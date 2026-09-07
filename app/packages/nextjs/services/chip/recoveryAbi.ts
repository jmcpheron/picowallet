export const recoveryAbi = [
  {
    type: "function",
    name: "startRecovery",
    stateMutability: "nonpayable",
    inputs: [
      { name: "newSignerX", type: "bytes32" },
      { name: "newSignerY", type: "bytes32" },
    ],
    outputs: [],
  },
  {
    type: "function",
    name: "finalizeRecovery",
    stateMutability: "nonpayable",
    inputs: [],
    outputs: [],
  },
  {
    type: "function",
    name: "recoveryAddress",
    stateMutability: "view",
    inputs: [],
    outputs: [{ type: "address" }],
  },
  {
    type: "function",
    name: "pendingSignerX",
    stateMutability: "view",
    inputs: [],
    outputs: [{ type: "bytes32" }],
  },
  {
    type: "function",
    name: "pendingSignerY",
    stateMutability: "view",
    inputs: [],
    outputs: [{ type: "bytes32" }],
  },
  {
    type: "function",
    name: "recoveryExecuteAfter",
    stateMutability: "view",
    inputs: [],
    outputs: [{ type: "uint64" }],
  },
] as const;
