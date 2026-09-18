import { useEffect, useState } from "react";

import { listTenants, type Tenant } from "./api";
import Chat from "./components/Chat";
import Facts from "./components/Facts";
import TenantSelector from "./components/TenantSelector";

type Tab = "chat" | "facts";

function App() {
  // TEMPORARY (APPCE-53/54 scaffolding): the backend can't verify who's
  // calling yet, so the owner_uid is just typed in here. Replaced by a
  // real Google Sign-In identity once APPCE-54 lands.
  const [ownerUid, setOwnerUid] = useState("");
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("chat");

  useEffect(() => {
    if (!ownerUid) return;
    listTenants(ownerUid).then((fetched) => {
      setTenants(fetched);
      setSelectedTenantId(fetched[0]?.tenant_id ?? null);
    });
  }, [ownerUid]);

  return (
    <main>
      <h1>Anamnesis</h1>
      <p>Personal Project Context Engine</p>

      <label>
        Owner UID (temporary):{" "}
        <input value={ownerUid} onChange={(e) => setOwnerUid(e.target.value)} />
      </label>

      {ownerUid && (
        <TenantSelector tenants={tenants} selectedId={selectedTenantId} onSelect={setSelectedTenantId} />
      )}

      {selectedTenantId && (
        <>
          <div>
            <button onClick={() => setTab("chat")}>Chat</button>
            <button onClick={() => setTab("facts")}>Facts</button>
          </div>

          {tab === "chat" && <Chat ownerUid={ownerUid} tenantId={selectedTenantId} />}
          {tab === "facts" && <Facts ownerUid={ownerUid} tenantId={selectedTenantId} />}
        </>
      )}
    </main>
  );
}

export default App;
