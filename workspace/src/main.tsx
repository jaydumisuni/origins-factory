import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import Phase5App from "./Phase5App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Origins workspace root element is missing");

createRoot(root).render(
  <StrictMode>
    <Phase5App />
  </StrictMode>,
);
