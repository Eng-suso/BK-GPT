# Simulation analytical canvas

The consultant observes a run, selects a task to diagnose it, configures a variant, compares final results and shares evidence. All existing tools remain available on one process workspace.

## Acceptance contract
- BPMN and analytical objects share a navigable scene. Opening an inspector cannot resize or remount the process.
- Explicit composition mode supports pointer and keyboard placement, undo, cancel and validated local persistence. Existing layouts migrate without losing widgets, expressions, filters or groups.
- Replay retains its clock when opening a tool. Final comparisons use complete-run summaries; they never masquerade as live replay.
- Process recovery, object navigation and zoom remain accessible even after panning away.
- Missing diagrams and unobserved metrics have explicit states. Small positive throughput must never display as zero.
- Desktop and mobile journeys, keyboard focus, reduced motion, accessibility and realistic BPMN layouts are verified before release.

## Architecture
A scene owns camera state and object positions. BPMN owns its internal model rendering and token overlays, without a competing navigation camera in scene mode. Run summaries remain the canonical source for final KPIs. Inspector panels overlay the scene; their visibility does not change scene dimensions. The existing scenario, heatmap, insights, comparison, analytics library and provenance tools remain accessible.


## Review and verification
The review corrected four failure modes: sampled final values masquerading as summary KPIs; missing observations appearing as zero or as improvements; screen targets shrinking with the scene; and mobile commands becoming unreachable beneath the inspector or outside the scene. Process actions now live in the scene toolbar. The mobile minimap is docked in that toolbar so it cannot cover object resize handles. Initial desktop zoom follows scene width, with a 75% floor, so shorter windows do not shrink analytical labels to fit the whole process vertically; the scene remains pannable. The viewport observer is installed once; replay frames do not recreate the camera or BPMN viewer. A pointer gesture commits one undoable layout change in world coordinates.

The UI journeys exercise Chrome and WebKit on desktop, Pixel 7 and iPhone 14. They include axe WCAG 2.2 scans in viewing/composition modes, keyboard placement, pointer movement at a non-default zoom, persisted coordinates, corrupt/blocked browser storage, eleven chart types, expressions, a two-lane BPMN with a gateway and loop, context tools without viewer remounts, and selecting B with or without its replay artifact. Mobile checks require more than 220 px of navigable process viewport; shorter screens scroll the workspace to retain usable controls. The 20 targeted editing/pins/comparison checks passed before the final whole-workspace matrix.

Commands:
- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run lint`
- `npm --prefix frontend run test:ci -- --maxWorkers=2`
- `npx playwright test --config playwright.simulation.config.ts --workers 1 --timeout 60000`
- `npm run check:bundle`

Build comparison used the same installed dependencies against archived `origin/main` (39f135e) and the integrated branch. Initial JavaScript stayed at 115.4 gzip kB. Total JavaScript changed from 977.4 to 982.8 gzip kB (+5.4 kB, +0.55%), in the lazy simulation route and its translations. Only the total bundle baseline was updated to the measured value; the 109.3 kB entry baseline and the existing 10% tolerance remain unchanged.

## Practical boundaries
Layout and pinned-analysis persistence remain local to the browser, matching the previous dashboard. Historical curves use the replay's sampled series; final global KPIs use canonical run summaries. Activity queue/WIP charts in final analysis show the end snapshot, not a recomputed aggregate. A missing replay leaves the model and summary KPIs available while replay-derived charts and activity counters show their missing-data state. No engine, API or server persistence contract changed.
