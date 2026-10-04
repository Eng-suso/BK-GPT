import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import type { ClaimRelation, ProjectSource } from "@/contracts/workspace";

const relationsQuery = vi.fn();

vi.mock("../api", () => ({
  useSourceRelationsQuery: (...args: unknown[]) => relationsQuery(...args),
}));

const { SourceRelationsSection } = await import("./SourceRelationsSection");

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
  reconcileStatus: "done",
};

const DIVERGENCE: ClaimRelation = {
  id: 1,
  kind: "divergence",
  divergenceType: "incompatible",
  reasons: [],
  explanation: "Le soglie di approvazione sono diverse.",
  claim: {
    claimId: 11,
    sourceId: "src-procedura",
    sourceName: "procedura.md",
    statement: "Il CFO approva gli ordini sopra i 30.000 EUR.",
    anchorRef: "§2",
    quote: "Il CFO approva gli ordini sopra i 30.000 EUR.",
    quoteVerified: true,
  },
  other: {
    claimId: 3,
    sourceId: "src-intervista",
    sourceName: "intervista.docx",
    statement: "Il CFO approva solo oltre 50.000 EUR.",
    anchorRef: "p.2",
    quote: "sopra i cinquantamila li vede il CFO",
    quoteVerified: false,
  },
};

const CORROBORATION: ClaimRelation = {
  ...DIVERGENCE,
  id: 2,
  kind: "corroboration",
  divergenceType: null,
  claim: { ...DIVERGENCE.claim, claimId: 12, statement: "Le fatture si registrano in SAP." },
  other: { ...DIVERGENCE.other, claimId: 4, anchorRef: "p.5" },
};

describe("SourceRelationsSection", () => {
  it("una divergenza mostra le due affermazioni, ognuna con file, ancora e citazione", () => {
    relationsQuery.mockReturnValue({ isLoading: false, isError: false, data: [DIVERGENCE, CORROBORATION] });
    render(<SourceRelationsSection source={SOURCE} />);

    const item = screen.getByText("Incompatibili").closest("li") as HTMLElement;
    expect(within(item).getByText("Questo file")).toBeInTheDocument();
    expect(within(item).getByText("intervista.docx")).toBeInTheDocument();
    expect(within(item).getByText("Il CFO approva solo oltre 50.000 EUR.")).toBeInTheDocument();
    expect(within(item).getByText("p.2")).toBeInTheDocument();
    expect(within(item).getByText("citazione da controllare")).toBeInTheDocument();
    expect(within(item).getByText("Le soglie di approvazione sono diverse.")).toBeInTheDocument();

    expect(screen.getByText("Divergenze (1)")).toBeInTheDocument();
    expect(screen.getByText("Confermate da altri file (1)")).toBeInTheDocument();
    expect(screen.getByText("Confermata da intervista.docx")).toBeInTheDocument();
  });

  it("dice quando le regole hanno indebolito una divergenza", () => {
    relationsQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [{ ...DIVERGENCE, divergenceType: "scope_difference", reasons: ["ambiti diversi"] }],
    });
    render(<SourceRelationsSection source={SOURCE} />);
    expect(screen.getByText("Ambiti diversi")).toBeInTheDocument();
    expect(screen.getByText(/più grave: ambiti diversi/)).toBeInTheDocument();
  });

  it("durante il confronto lo dice; finito senza relazioni lo dice; un errore di lettura e' un errore", () => {
    relationsQuery.mockReturnValue({ isLoading: false, isError: false, data: undefined });
    const { rerender } = render(<SourceRelationsSection source={{ ...SOURCE, reconcileStatus: "pending" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("DeliR confronta");

    relationsQuery.mockReturnValue({ isLoading: false, isError: false, data: [] });
    rerender(<SourceRelationsSection source={SOURCE} />);
    expect(screen.getByText(/Nessun altro file/)).toBeInTheDocument();

    relationsQuery.mockReturnValue({ isLoading: false, isError: true, data: undefined });
    rerender(<SourceRelationsSection source={SOURCE} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Impossibile leggere il confronto");
  });

  it("un confronto fallito lo dice, e mostra le relazioni scritte da altri file", () => {
    relationsQuery.mockReturnValue({ isLoading: false, isError: false, data: [DIVERGENCE] });
    render(<SourceRelationsSection source={{ ...SOURCE, reconcileStatus: "failed" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Confronto non riuscito");
    expect(screen.getByText("Incompatibili")).toBeInTheDocument();
  });

  it("senza affermazioni o prima del confronto la sezione non c'e'", () => {
    relationsQuery.mockReturnValue({ isLoading: false, isError: false, data: undefined });
    const { container, rerender } = render(
      <SourceRelationsSection source={{ ...SOURCE, reconcileStatus: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(<SourceRelationsSection source={{ ...SOURCE, claimsStatus: "pending" }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
