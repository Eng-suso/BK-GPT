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
