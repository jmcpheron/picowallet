// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./DeployHelpers.s.sol";
import { MockUSDS } from "../contracts/MockUSDS.sol";
import { MockReverseRegistrar } from "../contracts/MockReverseRegistrar.sol";
import { ChipAccount } from "../contracts/ChipAccount.sol";

/**
 * @notice Deploys the demo: a mock USDS on local chains and the ChipAccount vault.
 *
 * Env (packages/foundry/.env):
 *   CHIP_PUBKEY_X / CHIP_PUBKEY_Y  initial P-256 public key.
 *   USDS_ADDRESS                   existing token to use (live chains). Unset on localhost → MockUSDS.
 *   ENS_REVERSE_REGISTRAR          ENS ReverseRegistrar. Unset on localhost → mock.
 *   RECOVERY_ADDRESS               Fixed recovery wallet. Unset on localhost → deployer.
 *
 * yarn deploy                       # localhost
 * yarn deploy --network sepolia     # live (needs a keystore, see yarn generate)
 */
contract DeployChipDemo is ScaffoldETHDeploy {
    function run() external ScaffoldEthDeployerRunner {
        bytes32 qx = vm.envBytes32("CHIP_PUBKEY_X");
        bytes32 qy = vm.envBytes32("CHIP_PUBKEY_Y");
        address usds = vm.envOr("USDS_ADDRESS", address(0));
        address reverseRegistrar = vm.envOr("ENS_REVERSE_REGISTRAR", address(0));
        address recoveryAddress = vm.envOr("RECOVERY_ADDRESS", address(0));
        bool deployMock = usds == address(0);

        if (deployMock) {
            require(block.chainid == 31337, "Set USDS_ADDRESS for live chains");
            MockUSDS mock = new MockUSDS();
            deployments.push(Deployment("MockUSDS", address(mock)));
            usds = address(mock);
        }

        if (reverseRegistrar == address(0)) {
            require(block.chainid == 31337, "Set ENS_REVERSE_REGISTRAR for live chains");
            MockReverseRegistrar mockReverse = new MockReverseRegistrar();
            deployments.push(Deployment("MockReverseRegistrar", address(mockReverse)));
            reverseRegistrar = address(mockReverse);
        }

        if (recoveryAddress == address(0)) {
            require(block.chainid == 31337, "Set RECOVERY_ADDRESS for live chains");
            recoveryAddress = deployer;
        }

        ChipAccount account = new ChipAccount(usds, reverseRegistrar, recoveryAddress, qx, qy);
        deployments.push(Deployment("ChipAccount", address(account)));

        if (deployMock) {
            MockUSDS(usds).mint(address(account), 1_000 ether); // 1,000 USDS of play money in the vault
            MockUSDS(usds).mint(deployer, 1_000 ether);
        }

        console.log("ChipAccount:", address(account));
        console.log("USDS:       ", usds);
        console.log("ENS reverse:", reverseRegistrar);
        console.log("Recovery:   ", recoveryAddress);
        console.log("Signer X:   ", vm.toString(qx));
        console.log("Signer Y:   ", vm.toString(qy));
    }
}
