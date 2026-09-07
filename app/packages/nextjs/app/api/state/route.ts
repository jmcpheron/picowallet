import { NextResponse } from "next/server";
import { expireStale } from "../requests/route";
import { Address, formatEther, formatUnits } from "viem";
import { chipAccount, isLocal, publicClient, targetChain, tokenBalance, tokenMeta } from "~~/services/chip/chain";
import { onchainNonce, onchainSigner, recoveryState, relayerAddress, relayerBalance } from "~~/services/chip/relay";
import { readStore } from "~~/services/chip/store";

export const dynamic = "force-dynamic";

// The wallet polls every 12 s and the UI every few seconds; on mainnet each poll is 4 RPC calls.
// Cache the chain reads briefly so a poll is fast (the Pico blocks on it) and Alchemy stays quiet.
const CHAIN_CACHE_MS = 5000;
let chainCache: { at: number; value: any } | undefined;
async function chainReads(address: Address) {
  if (chainCache && Date.now() - chainCache.at < CHAIN_CACHE_MS) return chainCache.value;
  const value = await Promise.all([
    onchainSigner(),
    onchainNonce(),
    tokenBalance(address),
    relayerBalance(),
    publicClient()
      .getEnsName({ address })
      .catch(() => null),
    recoveryState(),
  ]);
  chainCache = { at: Date.now(), value };
  return value;
}

/** One poll for the UI: device, vault, relay, queue. */
export async function GET() {
  try {
    expireStale();
    const { address } = chipAccount();
    const token = await tokenMeta();
    const [signer, nonce, balance, relayBal, ensName, recovery] = await chainReads(address);
    const { device, requests, commands } = readStore();
    const devicePaired =
      !!device?.qx &&
      !!device.qy &&
      signer.qx.toLowerCase() === device.qx.toLowerCase() &&
      signer.qy.toLowerCase() === device.qy.toLowerCase();
    return NextResponse.json({
      chain: { id: targetChain.id, name: targetChain.name, isLocal },
      account: {
        address,
        ensName,
        authorizationVersion: recovery.version.toString(),
        nonce: nonce.toString(),
        signer,
        balance: balance.toString(),
        balanceFormatted: formatUnits(balance, token.decimals),
      },
      token,
      relayer: { address: relayerAddress(), balanceFormatted: formatEther(relayBal) },
      recovery: recovery.recoveryAddress
        ? {
            address: recovery.recoveryAddress,
            pendingSignerX: recovery.pendingSignerX,
            pendingSignerY: recovery.pendingSignerY,
            executeAfter: recovery.executeAfter.toString(),
          }
        : undefined,
      device: device ? { ...device, paired: devicePaired } : undefined,
      requests,
      commands,
      now: Date.now(),
    });
  } catch (e: any) {
    return NextResponse.json({ error: e?.shortMessage || e?.message || String(e) }, { status: 500 });
  }
}
