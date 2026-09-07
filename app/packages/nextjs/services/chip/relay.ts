import { chipAccount, isLocal, publicClient, relayClient, relayerAddress, targetChain } from "./chain";
import { recoveryAbi } from "./recoveryAbi";
import { type Address, type Hex } from "viem";

/**
 * The relay: submits chip-signed transfers and pays the gas. It holds no tokens and cannot spend
 * the vault by itself — a bad relay can only refuse to relay.
 */

export const P256_N = BigInt("0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551");
const SUPPORTED_AUTHORIZATION_VERSIONS = new Set([3n, 4n, 5n]);
const AUTHORIZATION_VERSION_ABI = [
  {
    type: "function",
    name: "AUTHORIZATION_VERSION",
    stateMutability: "view",
    inputs: [],
    outputs: [{ type: "uint256" }],
  },
] as const;

let authorizationChecked = false;

export async function authorizationVersion(): Promise<bigint> {
  const { address } = chipAccount();
  return publicClient().readContract({
    address,
    abi: AUTHORIZATION_VERSION_ABI,
    functionName: "AUTHORIZATION_VERSION",
  });
}

/** Refuse to operate a legacy deployment whose signer can be changed by an admin. */
export async function assertImmutableAuthorization(): Promise<void> {
  if (authorizationChecked) return;
  let version: bigint;
  try {
    version = await authorizationVersion();
  } catch {
    throw new Error("Unsafe legacy ChipAccount deployment. Redeploy authorization version 3 or newer.");
  }
  if (!SUPPORTED_AUTHORIZATION_VERSIONS.has(version)) {
    throw new Error(`Unsupported ChipAccount authorization version ${version}`);
  }
  authorizationChecked = true;
}

export async function recoveryState() {
  const version = await authorizationVersion();
  if (version < 5n)
    return {
      version,
      recoveryAddress: undefined,
      pendingSignerX: undefined,
      pendingSignerY: undefined,
      executeAfter: 0n,
    };
  const { address } = chipAccount();
  const pc = publicClient();
  const [recoveryAddress, pendingSignerX, pendingSignerY, executeAfter] = await Promise.all([
    pc.readContract({ address, abi: recoveryAbi, functionName: "recoveryAddress" }),
    pc.readContract({ address, abi: recoveryAbi, functionName: "pendingSignerX" }),
    pc.readContract({ address, abi: recoveryAbi, functionName: "pendingSignerY" }),
    pc.readContract({ address, abi: recoveryAbi, functionName: "recoveryExecuteAfter" }),
  ]);
  return { version, recoveryAddress, pendingSignerX, pendingSignerY, executeAfter };
}

/** OpenZeppelin's verifier rejects high-s. (r, N-s) is the same signature in canonical form. */
export function normalizeLowS(s: Hex): Hex {
  const v = BigInt(s);
  const canon = v > P256_N / 2n ? P256_N - v : v;
  return `0x${canon.toString(16).padStart(64, "0")}`;
}

export async function onchainSigner(): Promise<{ qx: Hex; qy: Hex; paired: boolean }> {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  const [qx, qy] = (await publicClient().readContract({ address, abi, functionName: "signer" })) as [Hex, Hex];
  const paired = BigInt(qx) !== 0n || BigInt(qy) !== 0n;
  return { qx, qy, paired };
}

export async function onchainNonce(): Promise<bigint> {
  const { address, abi } = chipAccount();
  return (await publicClient().readContract({ address, abi, functionName: "nonce" })) as bigint;
}

export async function contractDigest(
  token: Address,
  to: Address,
  amount: bigint,
  nonce: bigint,
  deadline: bigint,
): Promise<Hex> {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  return (await publicClient().readContract({
    address,
    abi,
    functionName: "hashTransfer",
    args: [token, to, amount, nonce, deadline],
  })) as Hex;
}

export async function isValidTransfer(token: Address, to: Address, amount: bigint, deadline: bigint, r: Hex, s: Hex) {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  return (await publicClient().readContract({
    address,
    abi,
    functionName: "isValidTransfer",
    args: [token, to, amount, deadline, r, s],
  })) as boolean;
}

export async function contractNameDigest(name: string, nonce: bigint, deadline: bigint): Promise<Hex> {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  return (await publicClient().readContract({
    address,
    abi,
    functionName: "hashSetName",
    args: [name, nonce, deadline],
  })) as Hex;
}

export async function isValidSetName(name: string, deadline: bigint, r: Hex, s: Hex) {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  return (await publicClient().readContract({
    address,
    abi,
    functionName: "isValidSetName",
    args: [name, deadline, r, s],
  })) as boolean;
}

export async function contractExecuteDigest(
  target: Address,
  value: bigint,
  data: Hex,
  nonce: bigint,
  deadline: bigint,
): Promise<Hex> {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  return (await publicClient().readContract({
    address,
    abi,
    functionName: "hashExecute",
    args: [target, value, data, nonce, deadline],
  })) as Hex;
}

export async function isValidExecute(target: Address, value: bigint, data: Hex, deadline: bigint, r: Hex, s: Hex) {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  return (await publicClient().readContract({
    address,
    abi,
    functionName: "isValidExecute",
    args: [target, value, data, deadline, r, s],
  })) as boolean;
}

export async function contractCancelRecoveryDigest(nonce: bigint, deadline: bigint): Promise<Hex> {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  return (await publicClient().readContract({
    address,
    abi,
    functionName: "hashCancelRecovery",
    args: [nonce, deadline],
  })) as Hex;
}

export async function isValidCancelRecovery(deadline: bigint, r: Hex, s: Hex) {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  return (await publicClient().readContract({
    address,
    abi,
    functionName: "isValidCancelRecovery",
    args: [deadline, r, s],
  })) as boolean;
}

export async function executeTransfer(token: Address, to: Address, amount: bigint, deadline: bigint, r: Hex, s: Hex) {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  const wallet = relayClient();
  const pc = publicClient();
  const args = [token, to, amount, deadline, r, s] as const;
  // simulate first so a revert surfaces as a readable error instead of a burned tx
  await pc.simulateContract({ address, abi, functionName: "executeTransfer", args, account: wallet.account! });
  const hash = await wallet.writeContract({
    chain: targetChain,
    account: wallet.account!,
    address,
    abi,
    functionName: "executeTransfer",
    args,
  });
  const receipt = await pc.waitForTransactionReceipt({ hash });
  return { hash, receipt, relayer: relayerAddress() };
}

export async function executeSetName(name: string, deadline: bigint, r: Hex, s: Hex) {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  const wallet = relayClient();
  const pc = publicClient();
  const args = [name, deadline, r, s] as const;
  await pc.simulateContract({ address, abi, functionName: "executeSetName", args, account: wallet.account! });
  const hash = await wallet.writeContract({
    chain: targetChain,
    account: wallet.account!,
    address,
    abi,
    functionName: "executeSetName",
    args,
  });
  const receipt = await pc.waitForTransactionReceipt({ hash });
  return { hash, receipt, relayer: relayerAddress() };
}

export async function executeCall(target: Address, value: bigint, data: Hex, deadline: bigint, r: Hex, s: Hex) {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  const wallet = relayClient();
  const pc = publicClient();
  const args = [target, value, data, deadline, r, s] as const;
  await pc.simulateContract({ address, abi, functionName: "execute", args, account: wallet.account! });
  const hash = await wallet.writeContract({
    chain: targetChain,
    account: wallet.account!,
    address,
    abi,
    functionName: "execute",
    args,
  });
  const receipt = await pc.waitForTransactionReceipt({ hash });
  return { hash, receipt, relayer: relayerAddress() };
}

export async function executeCancelRecovery(deadline: bigint, r: Hex, s: Hex) {
  await assertImmutableAuthorization();
  const { address, abi } = chipAccount();
  const wallet = relayClient();
  const pc = publicClient();
  const args = [deadline, r, s] as const;
  await pc.simulateContract({ address, abi, functionName: "cancelRecovery", args, account: wallet.account! });
  const hash = await wallet.writeContract({
    chain: targetChain,
    account: wallet.account!,
    address,
    abi,
    functionName: "cancelRecovery",
    args,
  });
  const receipt = await pc.waitForTransactionReceipt({ hash });
  return { hash, receipt, relayer: relayerAddress() };
}

export async function relayerBalance(): Promise<bigint> {
  return publicClient().getBalance({ address: relayerAddress() });
}

export { isLocal, relayerAddress };
