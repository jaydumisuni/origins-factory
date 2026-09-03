import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import InstalledApp from "./InstalledApp";
import Phase7App from "./Phase7App";
import { establishInstalledSession } from "./installedBootstrap";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Origins workspace root element is missing");

async function boot(): Promise<void> {
  const session = await establishInstalledSession();
  createRoot(root!).render(
    <StrictMode>
      {session.installedProxy ? <InstalledApp sessionReady={session.authenticated} /> : <Phase7App />}
    </StrictMode>,
  );
}

void boot();
