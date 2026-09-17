export type RequestStatus = "pending" | "signed" | "relaying" | "confirmed" | "failed" | "expired" | "rejected";

type RequestBase = {
  id: string;
  kind: "transfer" | "setName" | "execute" | "cancelRecovery";
  chainId: number;
  account: `0x${string}`; // the ChipAccount this request is for
  createdAt: number;
  updatedAt: number;
  status: RequestStatus;
  nonce: string;
  deadline: number; // unix seconds
  digest: `0x${string}`;
  signature?: { r: `0x${string}`; s: `0x${string}` };
  signedAt?: number;
  txHash?: `0x${string}`;
  blockNumber?: string;
  gasUsed?: string;
  relayer?: `0x${string}`;
  error?: string;
};

export type TransferRequest = RequestBase & {
  kind: "transfer";
  token: `0x${string}`;
  tokenSymbol: string;
  tokenDecimals: number;
  to: `0x${string}`;
  toName?: string;
  amount: string; // base units, as a decimal string
  amountFormatted: string;
};

export type SetNameRequest = RequestBase & { kind: "setName"; name: string };
export type ExecuteRequest = RequestBase & {
  kind: "execute";
  target: `0x${string}`;
  value: string; // wei
  valueFormatted: string; // ETH
  data: `0x${string}`;
  selector: `0x${string}`;
  dataHash: `0x${string}`;
};
export type CancelRecoveryRequest = RequestBase & { kind: "cancelRecovery" };
export type WalletRequest = TransferRequest | SetNameRequest | ExecuteRequest | CancelRecoveryRequest;

/** One P-256 slot of the chip's slot table, as the wallet reports it on announce. */
export type ChipSlot = {
  slot: number;
  kind: string;
  hasKey: boolean;
  locked: boolean;
  genKey?: boolean;
  lockable?: boolean;
  fingerprint?: string;
};

export type ChipStatus = {
  serial?: string;
  revision?: string;
  configLocked?: boolean;
  dataLocked?: boolean;
  slot?: number;
  activeSlot?: number;
  fingerprint?: string;
  hasKey?: boolean;
  slots?: ChipSlot[];
  note?: string;
};

export type DeviceInfo = {
  name: string;
  backend: string;
  qx?: `0x${string}`; // absent until the chip has a key
  qy?: `0x${string}`;
  firstSeen: number;
  lastSeen: number;
  chip?: ChipStatus;
};

export type CommandType = "status" | "genkey" | "lock-config";

/** A job for the Pi. The browser creates it, the Pi polls, runs it, posts the result. */
export type Command = {
  id: string;
  type: CommandType;
  createdAt: number;
  status: "pending" | "running" | "done" | "failed";
  result?: unknown;
  error?: string;
  doneAt?: number;
};

export type Store = {
  device?: DeviceInfo;
  requests: WalletRequest[];
  commands: Command[];
};
