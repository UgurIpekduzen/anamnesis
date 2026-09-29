import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./index.css";

const root = ReactDOM.createRoot(document.getElementById("root") as HTMLElement);

// A dev-only page for checking the Trace tab against static
// data. import.meta.env.DEV is false in a production build, so the branch
// and the demo code behind it are dropped from the bundle.
if (import.meta.env.DEV && window.location.pathname === "/trace-demo") {
  import("./dev/TraceDemo").then(({ default: TraceDemo }) => root.render(<TraceDemo />));
} else {
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
