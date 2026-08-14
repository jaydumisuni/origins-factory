import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import Phase4App from "./Phase4App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Origins workspace root element is missing");

createRoot(root).render(
  <StrictMode>
    <Phase4App />
  </StrictMode>,
);
