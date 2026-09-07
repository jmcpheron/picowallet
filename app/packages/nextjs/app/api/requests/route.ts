import { NextRequest, NextResponse } from "next/server";
import {
  type Address,
  type Hex,
  formatEther,
  formatUnits,
  getAddress,
  hashTypedData,
  isAddress,
  keccak256,
  parseEther,
  parseUnits,
} from "viem";
import { chipAccount, targetChain, tokenBalance, tokenMeta } from "~~/services/chip/chain";
import {
  contractCancelRecoveryDigest,
  contractDigest,
  contractExecuteDigest,
  contractNameDigest,
  onchainNonce,
} from "~~/services/chip/relay";
import { readStore, updateStore } from "~~/services/chip/store";
import { CancelRecoveryRequest, ExecuteRequest, SetNameRequest, TransferRequest } from "~~/services/chip/types";

export const dynamic = "force-dynamic";

const DEADLINE_SECONDS = Number(process.env.CHIP_REQUEST_TTL_SECONDS || 10 * 60);
const IN_FLIGHT = new Set(["pending", "signed", "relaying"]);

/** Mark pending requests whose deadline passed. Idempotent, cheap. */
export function expireStale() {
  const now = Math.floor(Date.now() / 1000);
  const store = readStore();
  if (!store.requests.some(r => r.status === "pending" && r.deadline < now)) return;
  updateStore(s => {
    for (const r of s.requests) {
      if (r.status === "pending" && r.deadline < now) {
        r.status = "expired";
        r.error = "not signed before the deadline";
        r.updatedAt = Date.now();
      }
    }
  });
}

/** List requests. The Pi polls `?status=pending`; the UI reads everything. */
export async function GET(req: NextRequest) {
  expireStale();
  const status = req.nextUrl.searchParams.get("status");
  let requests = readStore().requests;
  if (status) requests = requests.filter(r => r.status === status);
  if (status === "pending") requests = [...requests].sort((a, b) => a.createdAt - b.createdAt); // sign oldest first
  return NextResponse.json({ requests });
}

/** Create a transfer request: computes the EIP-712 digest the chip will sign. */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { to, toName, amount } = body as { to?: string; toName?: string; amount?: string };

  if (body.kind === "cancelRecovery") {
    expireStale();
    const inFlight = readStore().requests.filter(r => IN_FLIGHT.has(r.status));
    const { address: account } = chipAccount();
    const nonce = (await onchainNonce()) + BigInt(inFlight.length);
    const deadline = BigInt(Math.floor(Date.now() / 1000) + DEADLINE_SECONDS);
    const digest = hashTypedData({
      domain: { name: "ChipAccount", version: "1", chainId: targetChain.id, verifyingContract: account },
      types: {
        CancelRecovery: [
          { name: "nonce", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      },
      primaryType: "CancelRecovery",
      message: { nonce, deadline },
    });
    const fromContract = await contractCancelRecoveryDigest(nonce, deadline);
    if (fromContract.toLowerCase() !== digest.toLowerCase()) {
      return NextResponse.json(
        { error: `digest mismatch: viem ${digest} vs contract ${fromContract}` },
        { status: 500 },
      );
    }
    const now = Date.now();
    const request: CancelRecoveryRequest = {
      id: `${now.toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      kind: "cancelRecovery",
      chainId: targetChain.id,
      account: account as `0x${string}`,
      createdAt: now,
      updatedAt: now,
      status: "pending",
      nonce: nonce.toString(),
      deadline: Number(deadline),
      digest,
    };
    updateStore(store => store.requests.push(request));
    return NextResponse.json({ request }, { status: 201 });
  }

  if (body.kind === "execute") {
    if (typeof body.target !== "string" || !isAddress(body.target)) {
      return NextResponse.json({ error: "target must be an address" }, { status: 400 });
    }
    const data = typeof body.data === "string" ? body.data : "";
    if (!/^0x(?:[0-9a-fA-F]{2})*$/.test(data) || data.length > 16_386) {
      return NextResponse.json({ error: "calldata must be even-length hex, at most 8 KB" }, { status: 400 });
    }
    let value: bigint;
    try {
      value = parseEther(typeof body.valueEth === "string" && body.valueEth.trim() ? body.valueEth.trim() : "0");
    } catch {
      return NextResponse.json({ error: "ETH value must be a decimal number" }, { status: 400 });
    }
    if (value < 0n) return NextResponse.json({ error: "ETH value cannot be negative" }, { status: 400 });

    expireStale();
    const inFlight = readStore().requests.filter(r => IN_FLIGHT.has(r.status));
    const { address: account } = chipAccount();
    const nonce = (await onchainNonce()) + BigInt(inFlight.length);
    const deadline = BigInt(Math.floor(Date.now() / 1000) + DEADLINE_SECONDS);
    const target = getAddress(body.target) as Address;
    const callData = data as Hex;
    const digest = hashTypedData({
      domain: { name: "ChipAccount", version: "1", chainId: targetChain.id, verifyingContract: account },
      types: {
        Execute: [
          { name: "target", type: "address" },
          { name: "value", type: "uint256" },
          { name: "data", type: "bytes" },
          { name: "nonce", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      },
      primaryType: "Execute",
      message: { target, value, data: callData, nonce, deadline },
    });
    const fromContract = await contractExecuteDigest(target, value, callData, nonce, deadline);
    if (fromContract.toLowerCase() !== digest.toLowerCase()) {
      return NextResponse.json(
        { error: `digest mismatch: viem ${digest} vs contract ${fromContract}` },
        { status: 500 },
      );
    }

    const now = Date.now();
    const request: ExecuteRequest = {
      id: `${now.toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      kind: "execute",
      chainId: targetChain.id,
      account: account as `0x${string}`,
      createdAt: now,
      updatedAt: now,
      status: "pending",
      target: target as `0x${string}`,
      value: value.toString(),
      valueFormatted: formatEther(value),
      data: callData,
      selector: callData.length >= 10 ? (callData.slice(0, 10) as Hex) : "0x00000000",
      dataHash: keccak256(callData),
      nonce: nonce.toString(),
      deadline: Number(deadline),
      digest,
    };
    updateStore(store => store.requests.push(request));
    return NextResponse.json({ request }, { status: 201 });
  }

  if (body.kind === "setName") {
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const validName = /^(?=.{1,128}$)(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(name);
    if (!validName) {
      return NextResponse.json({ error: "use a lowercase ASCII ENS name, like hard.atg.eth" }, { status: 400 });
    }

    expireStale();
    const inFlight = readStore().requests.filter(r => IN_FLIGHT.has(r.status));
    const { address: account } = chipAccount();
    const nonce = (await onchainNonce()) + BigInt(inFlight.length);
    const deadline = BigInt(Math.floor(Date.now() / 1000) + DEADLINE_SECONDS);
    const digest = hashTypedData({
      domain: { name: "ChipAccount", version: "1", chainId: targetChain.id, verifyingContract: account },
      types: {
        SetName: [
          { name: "name", type: "string" },
          { name: "nonce", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      },
      primaryType: "SetName",
      message: { name, nonce, deadline },
    });
    const fromContract = await contractNameDigest(name, nonce, deadline);
    if (fromContract.toLowerCase() !== digest.toLowerCase()) {
      return NextResponse.json(
        { error: `digest mismatch: viem ${digest} vs contract ${fromContract}` },
        { status: 500 },
      );
    }

    const now = Date.now();
    const request: SetNameRequest = {
      id: `${now.toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      kind: "setName",
      chainId: targetChain.id,
      account: account as `0x${string}`,
      createdAt: now,
      updatedAt: now,
      status: "pending",
      name,
      nonce: nonce.toString(),
      deadline: Number(deadline),
      digest,
    };
    updateStore(store => store.requests.push(request));
    return NextResponse.json({ request }, { status: 201 });
  }

  if (!to || !isAddress(to)) return NextResponse.json({ error: "`to` must be a resolved address" }, { status: 400 });
  if (typeof amount !== "string" || !/^\d+(\.\d+)?$/.test(amount.trim())) {
    return NextResponse.json({ error: '`amount` must be a decimal string like "5"' }, { status: 400 });
  }

  const token = await tokenMeta();
  let units: bigint;
  try {
    units = parseUnits(amount.trim(), token.decimals);
  } catch {
    return NextResponse.json({ error: "amount has too many decimals" }, { status: 400 });
  }
  if (units <= 0n) return NextResponse.json({ error: "amount must be greater than zero" }, { status: 400 });

  const { address: account } = chipAccount();
  const balance = await tokenBalance(account);
  expireStale();
  const inFlight = readStore().requests.filter(r => IN_FLIGHT.has(r.status));
  const committed = inFlight.reduce((sum, r) => sum + (r.kind === "transfer" ? BigInt(r.amount) : 0n), 0n);
  if (units + committed > balance) {
    return NextResponse.json(
      {
        error:
          `vault holds ${formatUnits(balance, token.decimals)} ${token.symbol}` +
          (committed > 0n ? ` with ${formatUnits(committed, token.decimals)} already queued` : ""),
      },
      { status: 400 },
    );
  }

  // Nonce: the onchain nonce plus anything already queued ahead of this request.
  const nonce = (await onchainNonce()) + BigInt(inFlight.length);
  const deadline = BigInt(Math.floor(Date.now() / 1000) + DEADLINE_SECONDS);
  const toAddr = getAddress(to);

  // Compute the digest offchain (viem) and cross-check with the contract's own hashTransfer().
  const digest = hashTypedData({
    domain: { name: "ChipAccount", version: "1", chainId: targetChain.id, verifyingContract: account },
    types: {
      Transfer: [
        { name: "token", type: "address" },
        { name: "to", type: "address" },
        { name: "amount", type: "uint256" },
        { name: "nonce", type: "uint256" },
        { name: "deadline", type: "uint256" },
      ],
    },
    primaryType: "Transfer",
    message: { token: token.address, to: toAddr, amount: units, nonce, deadline },
  });
  const fromContract = await contractDigest(token.address, toAddr, units, nonce, deadline);
  if (fromContract.toLowerCase() !== digest.toLowerCase()) {
    return NextResponse.json({ error: `digest mismatch: viem ${digest} vs contract ${fromContract}` }, { status: 500 });
  }

  const now = Date.now();
  const request: TransferRequest = {
    id: `${now.toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    kind: "transfer",
    chainId: targetChain.id,
    account: account as `0x${string}`,
    createdAt: now,
    updatedAt: now,
    status: "pending",
    token: token.address as `0x${string}`,
    tokenSymbol: token.symbol,
    tokenDecimals: token.decimals,
    to: toAddr as `0x${string}`,
    toName: typeof toName === "string" && toName.trim() ? toName.trim().slice(0, 128) : undefined,
    amount: units.toString(),
    amountFormatted: formatUnits(units, token.decimals),
    nonce: nonce.toString(),
    deadline: Number(deadline),
    digest,
  };
  updateStore(store => {
    store.requests.push(request);
  });
  return NextResponse.json({ request }, { status: 201 });
}
