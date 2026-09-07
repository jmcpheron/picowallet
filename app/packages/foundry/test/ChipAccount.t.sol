// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import { P256 } from "@openzeppelin/contracts/utils/cryptography/P256.sol";
import { ChipAccount } from "../contracts/ChipAccount.sol";
import { MockUSDS } from "../contracts/MockUSDS.sol";
import { MockReverseRegistrar } from "../contracts/MockReverseRegistrar.sol";

contract CallTarget {
    uint256 public value;

    function setValue(uint256 newValue) external payable returns (uint256) {
        value = newValue;
        return newValue + 1;
    }

    function fail() external pure {
        revert("target failed");
    }
}

/// @dev Signatures come from pi/signer.py in --mock mode (ffi). Same code path the Pi runs, minus the chip.
contract ChipAccountTest is Test {
    string constant SIGNER = "../../../reference/pi/signer.py";
    string constant KEY = "1111111111111111111111111111111111111111111111111111111111111111";
    string constant OTHER_KEY = "2222222222222222222222222222222222222222222222222222222222222222";

    ChipAccount account;
    MockUSDS usds;
    MockReverseRegistrar reverseRegistrar;
    address relayer = makeAddr("relayer");
    address alice = makeAddr("alice");
    address recovery = makeAddr("recovery");
    bytes32 qx;
    bytes32 qy;

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

    function setUp() public {
        (qx, qy) = pubkey(KEY);
        usds = new MockUSDS();
        reverseRegistrar = new MockReverseRegistrar();
        account = new ChipAccount(address(usds), address(reverseRegistrar), recovery, qx, qy);
        usds.mint(address(account), 1_000 ether);
    }

    // ------------------------------------------------------------ helpers (ffi -> python)

    function pubkey(string memory key) internal returns (bytes32 x, bytes32 y) {
        string[] memory cmd = new string[](7);
        cmd[0] = "python3";
        cmd[1] = SIGNER;
        cmd[2] = "--mock";
        cmd[3] = "--mock-key";
        cmd[4] = key;
        cmd[5] = "--raw";
        cmd[6] = "pubkey";
        bytes memory out = vm.ffi(cmd);
        assertEq(out.length, 64, "pubkey ffi");
        (x, y) = abi.decode(out, (bytes32, bytes32));
    }

    function sign(string memory key, bytes32 digest) internal returns (bytes32 r, bytes32 s) {
        string[] memory cmd = new string[](9);
        cmd[0] = "python3";
        cmd[1] = SIGNER;
        cmd[2] = "--mock";
        cmd[3] = "--mock-key";
        cmd[4] = key;
        cmd[5] = "--raw";
        cmd[6] = "sign";
        cmd[7] = "--digest";
        cmd[8] = vm.toString(digest);
        bytes memory out = vm.ffi(cmd);
        assertEq(out.length, 64, "sign ffi");
        (r, s) = abi.decode(out, (bytes32, bytes32));
    }

    function signedTransfer(string memory key, address to, uint256 amount, uint256 deadline)
        internal
        returns (bytes32 r, bytes32 s)
    {
        bytes32 digest = account.hashTransfer(address(usds), to, amount, account.nonce(), deadline);
        return sign(key, digest);
    }

    function signedName(string memory key, string memory name, uint256 deadline)
        internal
        returns (bytes32 r, bytes32 s)
    {
        return sign(key, account.hashSetName(name, account.nonce(), deadline));
    }

    function signedExecute(string memory key, address target, uint256 value, bytes memory data, uint256 deadline)
        internal
        returns (bytes32 r, bytes32 s)
    {
        return sign(key, account.hashExecute(target, value, data, account.nonce(), deadline));
    }

    function signedCancelRecovery(string memory key, uint256 deadline) internal returns (bytes32 r, bytes32 s) {
        return sign(key, account.hashCancelRecovery(account.nonce(), deadline));
    }

    // ------------------------------------------------------------ tests

    function test_executeTransfer_movesTokensAndBumpsNonce() public {
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedTransfer(KEY, alice, 5 ether, deadline);

        assertTrue(account.isValidTransfer(address(usds), alice, 5 ether, deadline, r, s));

        vm.expectEmit(true, true, true, true);
        emit TransferExecuted(address(usds), alice, 5 ether, 0, relayer);
        vm.prank(relayer); // relay pays gas, holds no tokens, has no key
        account.executeTransfer(address(usds), alice, 5 ether, deadline, r, s);

        assertEq(usds.balanceOf(alice), 5 ether);
        assertEq(usds.balanceOf(address(account)), 995 ether);
        assertEq(account.nonce(), 1);
    }

    function test_replayIsRejected() public {
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedTransfer(KEY, alice, 5 ether, deadline);
        account.executeTransfer(address(usds), alice, 5 ether, deadline, r, s);

        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.executeTransfer(address(usds), alice, 5 ether, deadline, r, s);
        assertEq(usds.balanceOf(alice), 5 ether);
    }

    function test_tamperedAmountIsRejected() public {
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedTransfer(KEY, alice, 5 ether, deadline);
        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.executeTransfer(address(usds), alice, 6 ether, deadline, r, s);
    }

    function test_tamperedRecipientIsRejected() public {
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedTransfer(KEY, alice, 5 ether, deadline);
        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.executeTransfer(address(usds), relayer, 5 ether, deadline, r, s);
    }

    function test_wrongKeyIsRejected() public {
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedTransfer(OTHER_KEY, alice, 5 ether, deadline);
        assertFalse(account.isValidTransfer(address(usds), alice, 5 ether, deadline, r, s));
        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.executeTransfer(address(usds), alice, 5 ether, deadline, r, s);
    }

    function test_expiredIsRejected() public {
        uint256 deadline = block.timestamp + 1;
        (bytes32 r, bytes32 s) = signedTransfer(KEY, alice, 5 ether, deadline);
        vm.warp(deadline + 1);
        vm.expectRevert(abi.encodeWithSelector(ChipAccount.Expired.selector, deadline, deadline + 1));
        account.executeTransfer(address(usds), alice, 5 ether, deadline, r, s);
    }

    function test_insufficientBalanceReverts() public {
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedTransfer(KEY, alice, 1_001 ether, deadline);
        vm.expectRevert();
        account.executeTransfer(address(usds), alice, 1_001 ether, deadline, r, s);
        assertEq(account.nonce(), 0, "nonce must not advance on a failed transfer");
    }

    function test_signerIsConfiguredAtDeployment() public view {
        (bytes32 x, bytes32 y) = account.signer();
        assertEq(x, qx);
        assertEq(y, qy);
        assertEq(account.AUTHORIZATION_VERSION(), 5);
        assertEq(account.recoveryAddress(), recovery);
    }

    function test_constructorRejectsInvalidSigner() public {
        vm.expectRevert(ChipAccount.InvalidSigner.selector);
        new ChipAccount(address(usds), address(reverseRegistrar), recovery, bytes32(0), bytes32(0));

        vm.expectRevert(ChipAccount.InvalidSigner.selector);
        new ChipAccount(address(usds), address(reverseRegistrar), recovery, bytes32(uint256(1)), bytes32(uint256(2)));
    }

    function test_constructorRejectsNonContractToken() public {
        vm.expectRevert(ChipAccount.InvalidToken.selector);
        new ChipAccount(address(0), address(reverseRegistrar), recovery, qx, qy);
    }

    function test_constructorRejectsInvalidReverseRegistrar() public {
        vm.expectRevert(ChipAccount.InvalidReverseRegistrar.selector);
        new ChipAccount(address(usds), address(0), recovery, qx, qy);
    }

    function test_constructorRejectsZeroRecoveryAddress() public {
        vm.expectRevert(ChipAccount.ZeroAddress.selector);
        new ChipAccount(address(usds), address(reverseRegistrar), address(0), qx, qy);
    }

    function test_recoveryRotatesSignerOnlyAfterFourteenDays() public {
        (bytes32 newX, bytes32 newY) = pubkey(OTHER_KEY);
        vm.prank(recovery);
        account.startRecovery(newX, newY);
        uint256 executeAfter = block.timestamp + 14 days;
        assertEq(account.recoveryExecuteAfter(), executeAfter);
        assertEq(account.pendingSignerX(), newX);
        assertEq(account.pendingSignerY(), newY);

        vm.prank(recovery);
        vm.expectRevert(abi.encodeWithSelector(ChipAccount.RecoveryNotReady.selector, executeAfter, block.timestamp));
        account.finalizeRecovery();

        vm.warp(executeAfter);
        vm.prank(recovery);
        account.finalizeRecovery();
        (bytes32 finalX, bytes32 finalY) = account.signer();
        assertEq(finalX, newX);
        assertEq(finalY, newY);
        assertEq(account.recoveryExecuteAfter(), 0);

        uint256 oldKeyDeadline = block.timestamp + 10 minutes;
        (bytes32 oldR, bytes32 oldS) = signedTransfer(KEY, alice, 1 ether, oldKeyDeadline);
        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.executeTransfer(address(usds), alice, 1 ether, oldKeyDeadline, oldR, oldS);

        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedTransfer(OTHER_KEY, alice, 1 ether, deadline);
        account.executeTransfer(address(usds), alice, 1 ether, deadline, r, s);
        assertEq(usds.balanceOf(alice), 1 ether);
    }

    function test_recoveryCanOnlyBeStartedAndFinalizedByRecoveryAddress() public {
        (bytes32 newX, bytes32 newY) = pubkey(OTHER_KEY);
        vm.expectRevert(ChipAccount.OnlyRecoveryAddress.selector);
        account.startRecovery(newX, newY);

        vm.prank(recovery);
        account.startRecovery(newX, newY);
        vm.warp(account.recoveryExecuteAfter());
        vm.expectRevert(ChipAccount.OnlyRecoveryAddress.selector);
        account.finalizeRecovery();
    }

    function test_recoveryRejectsCurrentOrInvalidSigner() public {
        vm.startPrank(recovery);
        vm.expectRevert(ChipAccount.SameSigner.selector);
        account.startRecovery(qx, qy);
        vm.expectRevert(ChipAccount.InvalidSigner.selector);
        account.startRecovery(bytes32(0), bytes32(0));
        vm.stopPrank();
    }

    function test_restartingRecoveryResetsFullDelay() public {
        (bytes32 newX, bytes32 newY) = pubkey(OTHER_KEY);
        vm.prank(recovery);
        account.startRecovery(newX, newY);
        uint256 first = account.recoveryExecuteAfter();
        vm.warp(block.timestamp + 7 days);
        vm.prank(recovery);
        account.startRecovery(newX, newY);
        assertEq(account.recoveryExecuteAfter(), first + 7 days);
    }

    function test_validHardwareTransferCancelsRecovery() public {
        (bytes32 newX, bytes32 newY) = pubkey(OTHER_KEY);
        vm.prank(recovery);
        account.startRecovery(newX, newY);

        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedTransfer(KEY, alice, 1 ether, deadline);
        account.executeTransfer(address(usds), alice, 1 ether, deadline, r, s);

        assertEq(account.recoveryExecuteAfter(), 0);
        assertEq(account.pendingSignerX(), bytes32(0));
        assertEq(account.pendingSignerY(), bytes32(0));
    }

    function test_hardwareCanCancelRecoveryWithoutMovingFunds() public {
        (bytes32 newX, bytes32 newY) = pubkey(OTHER_KEY);
        vm.prank(recovery);
        account.startRecovery(newX, newY);

        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedCancelRecovery(KEY, deadline);
        account.cancelRecovery(deadline, r, s);

        assertEq(account.recoveryExecuteAfter(), 0);
        assertEq(account.nonce(), 1);
    }

    function test_badCancelSignatureDoesNotCancelRecovery() public {
        (bytes32 newX, bytes32 newY) = pubkey(OTHER_KEY);
        vm.prank(recovery);
        account.startRecovery(newX, newY);

        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedCancelRecovery(OTHER_KEY, deadline);
        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.cancelRecovery(deadline, r, s);
        assertGt(account.recoveryExecuteAfter(), 0);
    }

    function test_executeSetNameSetsReverseNameAndBumpsNonce() public {
        string memory name = "hard.atg.eth";
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedName(KEY, name, deadline);

        assertTrue(account.isValidSetName(name, deadline, r, s));
        bytes32 node = keccak256(abi.encodePacked(address(account)));
        vm.expectEmit(true, true, false, true);
        emit NameSet(name, node, 0, relayer);
        vm.prank(relayer);
        account.executeSetName(name, deadline, r, s);

        assertEq(reverseRegistrar.names(address(account)), name);
        assertEq(account.nonce(), 1);
    }

    function test_setNameTamperingAndReplayAreRejected() public {
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedName(KEY, "hard.atg.eth", deadline);
        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.executeSetName("fake.atg.eth", deadline, r, s);
        account.executeSetName("hard.atg.eth", deadline, r, s);
        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.executeSetName("hard.atg.eth", deadline, r, s);
    }

    function test_setNameRejectsUnsafeDisplayNames() public {
        for (uint256 i; i < 5; ++i) {
            string[5] memory bad = [string(""), ".atg.eth", "Hard.atg.eth", "hard..eth", "hard-.atg.eth"];
            vm.expectRevert(ChipAccount.InvalidName.selector);
            account.hashSetName(bad[i], 0, block.timestamp + 1);
        }
    }

    function test_otherTokenIsRejected() public {
        MockUSDS other = new MockUSDS();
        uint256 deadline = block.timestamp + 10 minutes;
        bytes32 digest = keccak256("not relevant");
        (bytes32 r, bytes32 s) = sign(KEY, digest);

        assertFalse(account.isValidTransfer(address(other), alice, 1 ether, deadline, r, s));
        vm.expectRevert(abi.encodeWithSelector(ChipAccount.UnsupportedToken.selector, address(other)));
        account.executeTransfer(address(other), alice, 1 ether, deadline, r, s);
    }

    function test_plainEthDepositIsAccepted() public {
        vm.deal(address(this), 1 ether);
        (bool ok,) = address(account).call{ value: 1 ether }("");
        assertTrue(ok);
        assertEq(address(account).balance, 1 ether);
    }

    function test_executeCallsContractAndReturnsData() public {
        CallTarget target = new CallTarget();
        bytes memory data = abi.encodeCall(target.setValue, (42));
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedExecute(KEY, address(target), 0, data, deadline);

        assertTrue(account.isValidExecute(address(target), 0, data, deadline, r, s));
        vm.expectEmit(true, true, true, true);
        emit CallExecuted(address(target), 0, target.setValue.selector, keccak256(data), 0, relayer);
        vm.prank(relayer);
        bytes memory result = account.execute(address(target), 0, data, deadline, r, s);

        assertEq(target.value(), 42);
        assertEq(abi.decode(result, (uint256)), 43);
        assertEq(account.nonce(), 1);
    }

    function test_executeCanRecoverAnyErc20() public {
        MockUSDS other = new MockUSDS();
        other.mint(address(account), 7 ether);
        bytes memory data = abi.encodeCall(other.transfer, (alice, 7 ether));
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedExecute(KEY, address(other), 0, data, deadline);

        account.execute(address(other), 0, data, deadline, r, s);
        assertEq(other.balanceOf(alice), 7 ether);
    }

    function test_executeCanSendEthToEoa() public {
        vm.deal(address(account), 1 ether);
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedExecute(KEY, alice, 0.4 ether, "", deadline);

        account.execute(alice, 0.4 ether, "", deadline, r, s);
        assertEq(alice.balance, 0.4 ether);
        assertEq(address(account).balance, 0.6 ether);
    }

    function test_executeRejectsTampering() public {
        CallTarget target = new CallTarget();
        bytes memory data = abi.encodeCall(target.setValue, (42));
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedExecute(KEY, address(target), 0, data, deadline);

        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.execute(address(target), 1, data, deadline, r, s);
        vm.expectRevert(ChipAccount.BadSignature.selector);
        account.execute(address(target), 0, abi.encodeCall(target.setValue, (43)), deadline, r, s);
    }

    function test_executeTargetFailureRollsBackNonce() public {
        CallTarget target = new CallTarget();
        bytes memory data = abi.encodeCall(target.fail, ());
        uint256 deadline = block.timestamp + 10 minutes;
        (bytes32 r, bytes32 s) = signedExecute(KEY, address(target), 0, data, deadline);

        vm.expectRevert("target failed");
        account.execute(address(target), 0, data, deadline, r, s);
        assertEq(account.nonce(), 0);
    }

    function test_executeDigestMatchesEip712() public view {
        bytes memory data = abi.encodeWithSignature("transfer(address,uint256)", alice, 7 ether);
        uint256 deadline = 1_900_000_000;
        bytes32 structHash = keccak256(
            abi.encode(account.EXECUTE_TYPEHASH(), address(usds), 0.1 ether, keccak256(data), uint256(0), deadline)
        );
        bytes32 expected = keccak256(abi.encodePacked("\x19\x01", account.domainSeparator(), structHash));
        assertEq(account.hashExecute(address(usds), 0.1 ether, data, 0, deadline), expected);
    }

    function test_executeRejectsZeroTarget() public {
        vm.expectRevert(ChipAccount.ZeroAddress.selector);
        account.hashExecute(address(0), 0, "", 0, block.timestamp + 1);
    }

    function test_digestMatchesEip712() public view {
        // Reproduce the digest the app computes offchain with viem's hashTypedData.
        uint256 deadline = 1_900_000_000;
        bytes32 structHash =
            keccak256(abi.encode(account.TRANSFER_TYPEHASH(), address(usds), alice, 5 ether, uint256(0), deadline));
        bytes32 expected = keccak256(abi.encodePacked("\x19\x01", account.domainSeparator(), structHash));
        assertEq(account.hashTransfer(address(usds), alice, 5 ether, 0, deadline), expected);
    }

    /// forge-config: default.fuzz.runs = 12
    function testFuzz_anyAmountUpToBalance(uint256 amount, address to) public {
        vm.assume(to != address(0) && to != address(account));
        amount = bound(amount, 0, 1_000 ether);
        uint256 deadline = block.timestamp + 10 minutes;
        uint256 before = usds.balanceOf(to);
        (bytes32 r, bytes32 s) = signedTransfer(KEY, to, amount, deadline);
        vm.prank(relayer);
        account.executeTransfer(address(usds), to, amount, deadline, r, s);
        assertEq(usds.balanceOf(to) - before, amount);
    }

    /// Known-answer vector (generated with python `cryptography`, low-s normalised) — exercises the
    /// OpenZeppelin verifier itself without ffi.
    function test_p256KnownAnswerVector() public view {
        bytes32 x = 0x0217e617f0b6443928278f96999e69a23a4f2c152bdf6d6cdf66e5b80282d4ed;
        bytes32 y = 0x194a7debcb97712d2dda3ca85aa8765a56f45fc758599652f2897c65306e5794;
        bytes32 h = 0x6d6f636b2d64696765737400000000000000000000000000000000000000abcd;
        bytes32 r = 0x4d80163031a75ade946ee6186599d84cfb057e7ad9bc84f2980768791f4ef508;
        bytes32 s = 0x3c5c7777a0c4df9ba7051f5534fca7dedb146e09e32987e3ba70db3dc096cf24;
        assertTrue(P256.verify(h, r, s, x, y));
        assertFalse(P256.verify(bytes32(uint256(h) ^ 1), r, s, x, y));
    }
}
