import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import Phase7App from "./Phase7App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Origins workspace root element is missing");

createRoot(root).render(
  <StrictMode>
    <Phase7App />
  </StrictMode>,
);
