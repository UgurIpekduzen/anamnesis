import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BrokenConnection } from "../../api";
import BrokenConnectionsSection from "./BrokenConnectionsSection";

const { getBrokenConnections } = vi.hoisted(() => ({ getBrokenConnections: vi.fn() }));

vi.mock("../../api", () => ({ getBrokenConnections }));

function connection(overrides: Partial<BrokenConnection> = {}): BrokenConnection {
  return {
    owner_uid: "owner-a",
    tenant_id: "bd2026",
    name: "BD2026",
    kind: "auth",
    failed_at: "2026-09-28T12:00:00+00:00",
    ...overrides,
  };
}

describe("BrokenConnectionsSection", () => {
  it("shows a healthy message when nothing is broken", async () => {
    getBrokenConnections.mockResolvedValue([]);

    render(<BrokenConnectionsSection idToken="token" />);

    expect(await screen.findByText("All connections are healthy.")).toBeInTheDocument();
  });

  it("lists each broken connection with a human-readable reason", async () => {
    getBrokenConnections.mockResolvedValue([connection()]);

    render(<BrokenConnectionsSection idToken="token" />);

    expect(await screen.findByText("BD2026")).toBeInTheDocument();
    expect(screen.getByText(/Token invalid or expired/)).toBeInTheDocument();
  });

  it("shows an error message when the connection status can't be loaded", async () => {
    getBrokenConnections.mockRejectedValue(new Error("boom"));

    render(<BrokenConnectionsSection idToken="token" />);

    expect(await screen.findByText("Couldn't load connection status.")).toBeInTheDocument();
    // The list itself never resolved, so there's nothing to say about it.
    expect(screen.queryByText("All connections are healthy.")).not.toBeInTheDocument();
  });
});
