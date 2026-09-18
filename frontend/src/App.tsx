import { useEffect, useState } from "react";

import { listTenants, type Tenant } from "./api";
import Auth from "./components/Auth";
import Chat from "./components/Chat";
import Facts from "./components/Facts";
import TenantSelector from "./components/TenantSelector";

type Tab = "chat" | "facts";

function decodeEmail(idToken: string): string {
  const payload = JSON.parse(atob(idToken.split(".")[1]));
  return payload.email;
}

function App() {
  const [idToken, setIdToken] = useState<string | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("chat");

  useEffect(() => {
    if (!idToken) return;
    listTenants(idToken).then((fetched) => {
      setTenants(fetched);
      setSelectedTenantId(fetched[0]?.tenant_id ?? null);
    });
  }, [idToken]);

  return (
    <main>
      <h1>Anamnesis</h1>
      <p>Personal Project Context Engine</p>

      {!idToken && <Auth onSignIn={setIdToken} />}
      {idToken && <p>Signed in as {decodeEmail(idToken)}</p>}

      {idToken && (
        <TenantSelector tenants={tenants} selectedId={selectedTenantId} onSelect={setSelectedTenantId} />
      )}

      {idToken && selectedTenantId && (
        <>
          <div>
            <button onClick={() => setTab("chat")}>Chat</button>
            <button onClick={() => setTab("facts")}>Facts</button>
          </div>

          {tab === "chat" && <Chat idToken={idToken} tenantId={selectedTenantId} />}
          {tab === "facts" && <Facts idToken={idToken} tenantId={selectedTenantId} />}
        </>
      )}
    </main>
  );
}

export default App;
