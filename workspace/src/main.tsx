import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import Phase6App from "./Phase6App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Origins workspace root element is missing");

createRoot(root).render(
  <StrictMode>
    <Phase6App />
  </StrictMode>,
);
