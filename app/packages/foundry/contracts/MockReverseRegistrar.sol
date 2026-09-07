// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MockReverseRegistrar {
    mapping(address => string) public names;

    function setName(string calldata name) external returns (bytes32 node) {
        names[msg.sender] = name;
        return keccak256(abi.encodePacked(msg.sender));
    }
}
