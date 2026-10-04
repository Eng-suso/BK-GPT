import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import type { ProjectSource, SourceClaim } from "@/contracts/workspace";

const claimsQuery = vi.fn();

vi.mock("../api", () => ({
  useSourceClaimsQuery: (...args: unknown[]) => claimsQuery(...args),
}));

const { SourceClaimsSection } = await import("./SourceClaimsSection");

const SOURCE: ProjectSource = {
  id: "src-procedura",
  projectId: "p-1",
  processId: "proc-1",
  name: "procedura.md",
  type: "File",
  meta: "",
  roles: ["process_evidence"],
  retention: "persistent",
  scopes: [],
  status: "approved",
  byteSize: 42,
  acquisitionStatus: "done",
  acquisitionError: null,
  claimsStatus: "done",
  claimsError: null,
  reconcileStatus: null,
};

const CLAIMS: SourceClaim[] = [
  {
    id: 1,
    statement: "Gli ordini sopra i 30.000 EUR li approva il CFO.",
    anchorRef: "§2",
    quote: "Il CFO approva gli ordini sopra i 30.000 EUR.",
    quoteVerified: true,
  },
  { id: 2, statement: "Il buyer firma gli ordini.", anchorRef: "R4", quote: "firma il buyer", quoteVerified: false },
];

describe("SourceClaimsSection", () => {
  it("mostra ogni affermazione con la sua ancora e la sua citazione", () => {
    claimsQuery.mockReturnValue({ isLoading: false, data: CLAIMS });
    render(<SourceClaimsSection source={SOURCE} />);

    expect(screen.getByText("Gli ordini sopra i 30.000 EUR li approva il CFO.")).toBeInTheDocument();
    expect(screen.getByText("§2")).toBeInTheDocument();
    expect(screen.getByText("citazione verificata")).toBeInTheDocument();
    expect(screen.getByText("citazione da controllare")).toBeInTheDocument();
  });

  it("prima della conferma dice come far partire l'estrazione", () => {
    claimsQuery.mockReturnValue({ isLoading: false, data: undefined });
    render(<SourceClaimsSection source={{ ...SOURCE, status: "extracted", claimsStatus: null }} />);
    expect(screen.getByText(/quando usi il file come evidenza/)).toBeInTheDocument();
  });

  it("durante l'estrazione lo dice, e un errore porta il motivo", () => {
    claimsQuery.mockReturnValue({ isLoading: false, data: undefined });
    const { rerender } = render(<SourceClaimsSection source={{ ...SOURCE, claimsStatus: "pending" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("DeliR sta estraendo le affermazioni");

    rerender(<SourceClaimsSection source={{ ...SOURCE, claimsStatus: "failed", claimsError: "provider giu'" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("provider giu'");
  });

  it("estrazione finita: caricamento, nessuna affermazione, lettura fallita e avviso di documento lungo", () => {
    claimsQuery.mockReturnValue({ isLoading: true, isError: false, data: undefined });
    const { rerender } = render(<SourceClaimsSection source={SOURCE} />);
    expect(screen.getByText("Carico le affermazioni…")).toBeInTheDocument();

    claimsQuery.mockReturnValue({ isLoading: false, isError: false, data: [] });
    rerender(<SourceClaimsSection source={{ ...SOURCE, claimsError: "Lette le prime porzioni: 4 rimaste fuori." }} />);
    expect(screen.getByText(/non afferma niente/)).toBeInTheDocument();
    expect(screen.getByText(/4 rimaste fuori/)).toBeInTheDocument();

    claimsQuery.mockReturnValue({ isLoading: false, isError: true, data: undefined });
    rerender(<SourceClaimsSection source={SOURCE} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Impossibile leggere le affermazioni");
  });

  it("una fonte senza file non ha la sezione", () => {
    claimsQuery.mockReturnValue({ isLoading: false, data: undefined });
    const { container } = render(
      <SourceClaimsSection source={{ ...SOURCE, acquisitionStatus: null, claimsStatus: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
