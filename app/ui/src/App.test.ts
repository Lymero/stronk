import { fireEvent, render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import App from "./App.svelte";
import { MockBackend, scenarios } from "./lib/backend/mock.ts";
import { createApp } from "./lib/state/app.svelte.ts";

function setup(name: keyof typeof scenarios) {
  const backend = new MockBackend(scenarios[name]);
  const app = createApp(backend);
  const onstep = async () => {
    backend.step();
    await app.refresh();
  };
  render(App, { app, onstep });
  return { backend, app };
}

describe("App with MockBackend", () => {
  it("waits outside champion select", async () => {
    const { app } = setup("ranked-jungle");
    await app.refresh();
    expect(await screen.findByText("Waiting for champion select")).toBeInTheDocument();
    expect(screen.getByText("Data 16.20")).toBeInTheDocument();
  });

  it("loads the hovered champion's build, and lock-in reuses it", async () => {
    const { backend, app } = setup("ranked-jungle");
    await app.refresh();
    await fireEvent.click(screen.getByRole("button", { name: "Next step" }));
    expect(await screen.findByRole("heading", { name: "Graves" })).toBeInTheDocument();
    expect(screen.getByLabelText("Build")).toHaveTextContent("Patch 16.20");

    await fireEvent.click(screen.getByRole("button", { name: "Next step" }));
    expect(await screen.findByRole("heading", { name: "LeeSin" })).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Next step" }));
    expect(await screen.findByText(/Locked in/)).toBeInTheDocument();

    const fetched = backend.calls.filter((c) => c.id === "build.get").map((c) => c.params);
    expect(fetched).toEqual([
      { champion: "Graves", role: "JUNGLE" },
      { champion: "LeeSin", role: "JUNGLE" }, // once, while hovering: not again at lock-in
    ]);
  });

  it("shows flags instead of numbers it can't stand behind", async () => {
    const { app } = setup("ranked-jungle");
    await fireEvent.click(screen.getByRole("button", { name: "Next step" }));
    await app.refresh();
    expect((await screen.findAllByText("No comparison")).length).toBeGreaterThan(0);
  });

  it("says when the League client isn't running", async () => {
    const { app } = setup("no-client");
    await app.refresh();
    expect(await screen.findByRole("alert")).toHaveTextContent("is the League client running?");
  });

  it("refuses data that failed verification", async () => {
    const { app } = setup("bad-data");
    await app.refresh();
    expect(await screen.findByRole("alert")).toHaveTextContent("hash mismatch");
    expect(screen.queryByLabelText("Build")).not.toBeInTheDocument();
  });
});
