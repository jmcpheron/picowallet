// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import { EIP712 } from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import { P256 } from "@openzeppelin/contracts/utils/cryptography/P256.sol";
import { Address } from "@openzeppelin/contracts/utils/Address.sol";
import { ReentrancyGuard } from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface IReverseRegistrar {
    function setName(string calldata name) external returns (bytes32 node);
}

/**
 * @title ChipAccount
 * @notice A token vault owned by a NIST P-256 public key that lives inside an ATECC608 secure element.
 *
 *  The chip never touches the chain. It signs a 32-byte EIP-712 digest describing a token transfer
 *  (a meta-transaction). Anyone — in the demo, a relay that pays gas — submits the signature to
 *  `executeTransfer`, the contract verifies it against the chip's public key, and moves the tokens.
 *
 *  Why P-256 and not ecrecover: the ATECC608 only speaks secp256r1. Verification uses OpenZeppelin's
 *  P256 library, which calls the RIP-7212 / EIP-7951 precompile when the chain has it and falls back to a
 *  pure-Solidity verifier otherwise (local anvil works either way).
 */
contract ChipAccount is EIP712, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant TRANSFER_TYPEHASH =
        keccak256("Transfer(address token,address to,uint256 amount,uint256 nonce,uint256 deadline)");
    bytes32 public constant SET_NAME_TYPEHASH = keccak256("SetName(string name,uint256 nonce,uint256 deadline)");
    bytes32 public constant EXECUTE_TYPEHASH =
        keccak256("Execute(address target,uint256 value,bytes data,uint256 nonce,uint256 deadline)");
    bytes32 public constant CANCEL_RECOVERY_TYPEHASH = keccak256("CancelRecovery(uint256 nonce,uint256 deadline)");
    uint256 public constant RECOVERY_DELAY = 14 days;

    /// @notice Bumped when the authorization model changes. The app refuses legacy mutable-signer deployments.
    uint256 public constant AUTHORIZATION_VERSION = 5;

    /// @notice Current public key of the signing chip (P-256 affine coordinates).
    bytes32 public signerX;
    bytes32 public signerY;

    /// @notice Fixed recovery wallet. It can rotate the chip key only after the delay.
    address public immutable recoveryAddress;
    bytes32 public pendingSignerX;
    bytes32 public pendingSignerY;
    uint64 public recoveryExecuteAfter;

    /// @notice Token used by the simple transfer flow. General execution can call other token contracts.
    address public immutable token;

    /// @notice ENS reverse registrar used only to set this vault's primary name.
    address public immutable reverseRegistrar;

    /// @notice Replay protection. Each signed transfer must carry the current nonce.
    uint256 public nonce;

    event SignerConfigured(bytes32 indexed qx, bytes32 indexed qy);
    event TransferExecuted(
        address indexed token, address indexed to, uint256 amount, uint256 indexed nonce, address relayer
    );
    event NameSet(string name, bytes32 indexed node, uint256 indexed nonce, address relayer);
    event CallExecuted(
        address indexed target,
        uint256 value,
        bytes4 indexed selector,
        bytes32 dataHash,
        uint256 indexed nonce,
        address relayer
    );
    event EtherReceived(address indexed sender, uint256 amount);
    event RecoveryStarted(bytes32 indexed newSignerX, bytes32 indexed newSignerY, uint256 executeAfter);
    event RecoveryCancelled(bytes32 indexed pendingSignerX, bytes32 indexed pendingSignerY);
    event RecoveryFinalized(
        bytes32 indexed oldSignerX, bytes32 indexed oldSignerY, bytes32 newSignerX, bytes32 newSignerY
    );

    error InvalidSigner();
    error InvalidToken();
    error InvalidReverseRegistrar();
    error InvalidName();
    error UnsupportedToken(address token);
    error Expired(uint256 deadline, uint256 nowTs);
    error BadSignature();
    error ZeroAddress();
    error OnlyRecoveryAddress();
    error RecoveryNotPending();
    error RecoveryNotReady(uint256 executeAfter, uint256 nowTs);
    error SameSigner();

    constructor(address _token, address _reverseRegistrar, address _recoveryAddress, bytes32 _qx, bytes32 _qy)
        EIP712("ChipAccount", "1")
    {
        if (_token.code.length == 0) revert InvalidToken();
        if (_reverseRegistrar.code.length == 0) revert InvalidReverseRegistrar();
        if (_recoveryAddress == address(0)) revert ZeroAddress();
        if (!P256.isValidPublicKey(_qx, _qy)) revert InvalidSigner();
        token = _token;
        reverseRegistrar = _reverseRegistrar;
        recoveryAddress = _recoveryAddress;
        signerX = _qx;
        signerY = _qy;
        emit SignerConfigured(_qx, _qy);
    }

    // ---------------------------------------------------------------- views

    function signer() external view returns (bytes32 qx, bytes32 qy) {
        return (signerX, signerY);
    }

    function domainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }

    /// @notice The exact 32 bytes the chip signs for a given transfer.
    function hashTransfer(address _token, address to, uint256 amount, uint256 _nonce, uint256 deadline)
        public
        view
        returns (bytes32)
    {
        if (_token != token) revert UnsupportedToken(_token);
        return _hashTypedDataV4(keccak256(abi.encode(TRANSFER_TYPEHASH, _token, to, amount, _nonce, deadline)));
    }

    /// @notice Convenience: the digest for the *next* transfer (uses the current nonce).
    function nextTransferDigest(address _token, address to, uint256 amount, uint256 deadline)
        external
        view
        returns (bytes32 digest, uint256 currentNonce)
    {
        return (hashTransfer(_token, to, amount, nonce, deadline), nonce);
    }

    /// @notice The exact digest the chip signs to set this vault's ENS reverse name.
    function hashSetName(string calldata name, uint256 _nonce, uint256 deadline) public view returns (bytes32) {
        _validateName(name);
        return _hashTypedDataV4(keccak256(abi.encode(SET_NAME_TYPEHASH, keccak256(bytes(name)), _nonce, deadline)));
    }

    /// @notice The exact digest the chip signs for an arbitrary external call.
    function hashExecute(address target, uint256 value, bytes calldata data, uint256 _nonce, uint256 deadline)
        public
        view
        returns (bytes32)
    {
        if (target == address(0)) revert ZeroAddress();
        return
            _hashTypedDataV4(keccak256(abi.encode(EXECUTE_TYPEHASH, target, value, keccak256(data), _nonce, deadline)));
    }

    function hashCancelRecovery(uint256 _nonce, uint256 deadline) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(CANCEL_RECOVERY_TYPEHASH, _nonce, deadline)));
    }

    /// @notice Check a chip signature without spending gas on a transaction.
    function isValidTransfer(address _token, address to, uint256 amount, uint256 deadline, bytes32 r, bytes32 s)
        external
        view
        returns (bool)
    {
        if (_token != token) return false;
        return P256.verify(hashTransfer(_token, to, amount, nonce, deadline), r, s, signerX, signerY);
    }

    function isValidSetName(string calldata name, uint256 deadline, bytes32 r, bytes32 s) external view returns (bool) {
        return P256.verify(hashSetName(name, nonce, deadline), r, s, signerX, signerY);
    }

    function isValidExecute(address target, uint256 value, bytes calldata data, uint256 deadline, bytes32 r, bytes32 s)
        external
        view
        returns (bool)
    {
        return P256.verify(hashExecute(target, value, data, nonce, deadline), r, s, signerX, signerY);
    }

    function isValidCancelRecovery(uint256 deadline, bytes32 r, bytes32 s) external view returns (bool) {
        return P256.verify(hashCancelRecovery(nonce, deadline), r, s, signerX, signerY);
    }

    // ---------------------------------------------------------------- execute

    /**
     * @notice Settle a chip-signed transfer. Anyone may call; the caller pays gas.
     * @dev The signature must be over `hashTransfer(token, to, amount, nonce, deadline)` with the current
     *      nonce, and `s` must be in the lower half of the curve order (OpenZeppelin rejects high-s).
     */
    function executeTransfer(address _token, address to, uint256 amount, uint256 deadline, bytes32 r, bytes32 s)
        external
        nonReentrant
    {
        if (block.timestamp > deadline) revert Expired(deadline, block.timestamp);
        if (to == address(0)) revert ZeroAddress();
        if (_token != token) revert UnsupportedToken(_token);

        uint256 usedNonce = nonce;
        bytes32 digest = hashTransfer(_token, to, amount, usedNonce, deadline);
        _authorize(digest, r, s, usedNonce);
        IERC20(_token).safeTransfer(to, amount);
        emit TransferExecuted(_token, to, amount, usedNonce, msg.sender);
    }

    /**
     * @notice Set this vault's ENS primary name using a chip signature. Cannot call arbitrary contracts.
     */
    function executeSetName(string calldata name, uint256 deadline, bytes32 r, bytes32 s) external nonReentrant {
        if (block.timestamp > deadline) revert Expired(deadline, block.timestamp);

        uint256 usedNonce = nonce;
        bytes32 digest = hashSetName(name, usedNonce, deadline);
        _authorize(digest, r, s, usedNonce);
        bytes32 node = IReverseRegistrar(reverseRegistrar).setName(name);
        emit NameSet(name, node, usedNonce, msg.sender);
    }

    /**
     * @notice Execute any external call authorized by the chip.
     * @dev The signature commits to the exact target, ETH value, calldata, nonce, deadline, chain, and wallet.
     *      Nonce advances before the external call and the whole transaction reverts if the call fails.
     */
    function execute(address target, uint256 value, bytes calldata data, uint256 deadline, bytes32 r, bytes32 s)
        external
        nonReentrant
        returns (bytes memory result)
    {
        if (block.timestamp > deadline) revert Expired(deadline, block.timestamp);

        uint256 usedNonce = nonce;
        bytes32 digest = hashExecute(target, value, data, usedNonce, deadline);
        _authorize(digest, r, s, usedNonce);
        (bool success, bytes memory returndata) = target.call{ value: value }(data);
        result = Address.verifyCallResult(success, returndata);
        bytes4 selector = data.length >= 4 ? bytes4(data[:4]) : bytes4(0);
        emit CallExecuted(target, value, selector, keccak256(data), usedNonce, msg.sender);
    }

    /// @notice Start or replace a recovery request. Restarting resets the full delay.
    function startRecovery(bytes32 newSignerX, bytes32 newSignerY) external {
        if (msg.sender != recoveryAddress) revert OnlyRecoveryAddress();
        if (!P256.isValidPublicKey(newSignerX, newSignerY)) revert InvalidSigner();
        if (newSignerX == signerX && newSignerY == signerY) revert SameSigner();

        pendingSignerX = newSignerX;
        pendingSignerY = newSignerY;
        recoveryExecuteAfter = uint64(block.timestamp + RECOVERY_DELAY);
        emit RecoveryStarted(newSignerX, newSignerY, recoveryExecuteAfter);
    }

    /// @notice Complete recovery after the uninterrupted 14-day delay.
    function finalizeRecovery() external {
        if (msg.sender != recoveryAddress) revert OnlyRecoveryAddress();
        uint256 executeAfter = recoveryExecuteAfter;
        if (executeAfter == 0) revert RecoveryNotPending();
        if (block.timestamp < executeAfter) revert RecoveryNotReady(executeAfter, block.timestamp);

        bytes32 oldX = signerX;
        bytes32 oldY = signerY;
        signerX = pendingSignerX;
        signerY = pendingSignerY;
        _clearRecovery();
        emit RecoveryFinalized(oldX, oldY, signerX, signerY);
        emit SignerConfigured(signerX, signerY);
    }

    /// @notice Cancel a pending recovery without moving funds or calling another contract.
    function cancelRecovery(uint256 deadline, bytes32 r, bytes32 s) external nonReentrant {
        if (block.timestamp > deadline) revert Expired(deadline, block.timestamp);
        if (recoveryExecuteAfter == 0) revert RecoveryNotPending();
        uint256 usedNonce = nonce;
        _authorize(hashCancelRecovery(usedNonce, deadline), r, s, usedNonce);
    }

    receive() external payable {
        emit EtherReceived(msg.sender, msg.value);
    }

    function _authorize(bytes32 digest, bytes32 r, bytes32 s, uint256 usedNonce) internal {
        if (!P256.verify(digest, r, s, signerX, signerY)) revert BadSignature();
        nonce = usedNonce + 1;
        _cancelRecovery();
    }

    function _cancelRecovery() internal {
        if (recoveryExecuteAfter == 0) return;
        bytes32 pendingX = pendingSignerX;
        bytes32 pendingY = pendingSignerY;
        _clearRecovery();
        emit RecoveryCancelled(pendingX, pendingY);
    }

    function _clearRecovery() internal {
        pendingSignerX = bytes32(0);
        pendingSignerY = bytes32(0);
        recoveryExecuteAfter = 0;
    }

    /// @dev Restrict the tiny hardware display to unambiguous lowercase ASCII ENS names.
    function _validateName(string calldata name) internal pure {
        bytes calldata value = bytes(name);
        if (value.length == 0 || value.length > 128) revert InvalidName();
        bool labelStart = true;
        for (uint256 i; i < value.length; ++i) {
            bytes1 c = value[i];
            if (c == ".") {
                if (labelStart || value[i - 1] == "-") revert InvalidName();
                labelStart = true;
            } else {
                if (!((c >= "a" && c <= "z") || (c >= "0" && c <= "9") || (c == "-" && !labelStart))) {
                    revert InvalidName();
                }
                labelStart = false;
            }
        }
        if (labelStart || value[value.length - 1] == "-") revert InvalidName();
    }
}
