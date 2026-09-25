import { lazy } from "react";

/**
 * Le schermate del prodotto, caricate quando servono.
 *
 * Erano tutte importate in cima al router, quindi il primo caricamento portava
 * giù l'intero prodotto: `bpmn-js` con il pannello proprietà e la token
 * simulation, `recharts`, `react-markdown`. Chi apriva Clienti scaricava il
 * canvas BPMN prima di vedere una riga della tabella.
 *
 * `lazy` vuole un export di default e qui gli export hanno un nome: la
 * mappatura sta in queste righe e non nei moduli, perché il modo in cui il
 * router carica una schermata non è un fatto della schermata.
 *
 * Stanno in un file loro e non nel router perché un modulo che esporta
 * componenti e altro insieme rompe il fast refresh in sviluppo.
 */

export const HomePage = lazy(() =>
  import("@/features/home/HomePage").then((m) => ({ default: m.HomePage })),
);

export const ConsultantPage = lazy(() =>
  import("@/features/consultant/ConsultantPage").then((m) => ({
    default: m.ConsultantPage,
  })),
);

export const ClientsListPage = lazy(() =>
  import("@/features/clients").then((m) => ({ default: m.ClientsListPage })),
);

export const ProjectsListPage = lazy(() =>
  import("@/features/projects").then((m) => ({ default: m.ProjectsListPage })),
);

export const ProjectDetailPage = lazy(() =>
  import("@/features/projects").then((m) => ({ default: m.ProjectDetailPage })),
);

export const ProcessStudioPage = lazy(() =>
  import("@/features/process").then((m) => ({ default: m.ProcessStudioPage })),
);

export const ModelsPage = lazy(() =>
  import("@/features/models/ModelsPage").then((m) => ({ default: m.ModelsPage })),
);

export const ArchivePage = lazy(() =>
  import("@/features/archive/ArchivePage").then((m) => ({ default: m.ArchivePage })),
);

export const SettingsPage = lazy(() =>
  import("@/features/settings/SettingsPage").then((m) => ({
    default: m.SettingsPage,
  })),
);

// La sezione Simulazione è un blocco solo: si entra dalla Panoramica e si passa
// da una schermata all'altra con la barra, quindi spezzarla per pagina
// aggiungerebbe un'attesa a ogni passaggio senza risparmiare niente.
const simulation = () => import("@/features/process/simulation");

export const SimulationLayout = lazy(() =>
  simulation().then((m) => ({ default: m.SimulationLayout })),
);

export const SimulationOverviewPage = lazy(() =>
  simulation().then((m) => ({ default: m.SimulationOverviewPage })),
);

export const ScenarioBuilderPage = lazy(() =>
  simulation().then((m) => ({ default: m.ScenarioBuilderPage })),
);

export const ReplayPage = lazy(() =>
  simulation().then((m) => ({ default: m.ReplayPage })),
);

export const SimulationDashboardPage = lazy(() =>
  simulation().then((m) => ({ default: m.SimulationDashboardPage })),
);

export const HeatmapPage = lazy(() =>
  simulation().then((m) => ({ default: m.HeatmapPage })),
);

export const ComparePage = lazy(() =>
  simulation().then((m) => ({ default: m.ComparePage })),
);

export const InsightsPage = lazy(() =>
  simulation().then((m) => ({ default: m.InsightsPage })),
);
