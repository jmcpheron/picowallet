import { wagmiConnectors } from "./wagmiConnectors";
import { Chain, createClient, http } from "viem";
import { hardhat } from "viem/chains";
import { createConfig } from "wagmi";
import scaffoldConfig, { ScaffoldConfig } from "~~/scaffold.config";
import { getAlchemyHttpUrl } from "~~/utils/scaffold-eth";

const { targetNetworks } = scaffoldConfig;

// Do not add remote chains implicitly: every remote chain requires an explicit Alchemy-backed transport.
export const enabledChains = targetNetworks;

export const wagmiConfig = createConfig({
  chains: enabledChains,
  connectors: wagmiConnectors(),
  ssr: true,
  client: ({ chain }) => {
    if (chain.id === (hardhat as Chain).id) {
      return createClient({ chain, transport: http() });
    }
    const rpcOverrideUrl = (scaffoldConfig.rpcOverrides as ScaffoldConfig["rpcOverrides"])?.[chain.id];
    const rpcUrl = rpcOverrideUrl || getAlchemyHttpUrl(chain.id);
    if (!rpcUrl || !rpcUrl.startsWith("https://") || !new URL(rpcUrl).hostname.endsWith(".g.alchemy.com")) {
      throw new Error(`Set an Alchemy RPC for chain ${chain.id}; public RPC fallbacks are disabled`);
    }
    return createClient({
      chain,
      transport: http(rpcUrl),
      pollingInterval: scaffoldConfig.pollingInterval,
    });
  },
});
