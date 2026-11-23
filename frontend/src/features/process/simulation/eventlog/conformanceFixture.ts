import type { Conformance } from "./eventLogTypes";

/** Una conformance realistica per i test: 7 casi su 10 passano dal CFO. */
export const CONFORMANCE: Conformance = {
  event_log: {
    id: "elog_1", process_id: "acquisti", name: "erp.csv", format: "csv", delimiter: ";", byte_size: 1, row_count: 1,
    columns: [], status: "mapped", mapping: null, template: null, created_at: "2026-11-23T10:00:00Z", mapped_at: "2026-11-23T10:05:00Z",
  },
  bpmn_version_id: 3,
  mapping_bpmn_version_id: 3,
  fitness: 0.91,
  cases: 10,
  fitting_cases: 7,
  fitting_share: 0.7,
  deviations: [
    { element_id: "T2", name: "Approvazione CFO", executed_out_of_order: 0, left_waiting: 3 },
    { element_id: "T3", name: "Emissione ordine", executed_out_of_order: 3, left_waiting: 0 },
    { element_id: "Gateway_1", name: "Gateway_1", executed_out_of_order: 0, left_waiting: 3 },
  ],
  variants: [
    { activities: ["Richiesta", "Approvazione CFO", "Emissione ordine"], cases: 7, fitness: 1, fits: true, out_of_order: [], waiting: [], unmodeled: [] },
    { activities: ["Richiesta", "Emissione ordine"], cases: 3, fitness: 0.8, fits: false, out_of_order: ["T3"], waiting: ["T2", "Gateway_1"], unmodeled: [] },
  ],
  unmodeled_activities: {},
  unobserved_elements: [],
  excluded_variants: 0,
  excluded_cases: 0,
  warnings: [],
};
