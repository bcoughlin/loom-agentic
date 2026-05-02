/**
 * Sessions page — list of agent runs (sessions) with detail pane.
 *
 * Placeholder. The two-column list+detail UI will be built in plan_3
 * step 5 (extract SessionList + SessionDetail components from powra's
 * AdminAgentRuns pattern). Once serve.py exists (plan_3 step 7), this
 * page consumes /api/runs to populate the list.
 */
export default function Sessions() {
  return (
    <div style={styles.empty}>
      <div style={styles.title}>Sessions</div>
      <div style={styles.hint}>
        Two-column list+detail view of agent runs.
        <br/>
        Wired in plan_3 step 5 (SessionList) + step 7 (serve.py /api/runs).
      </div>
    </div>
  )
}

const styles = {
  empty: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, color: '#888', fontFamily: 'monospace', padding: 40 },
  title: { fontSize: 20, color: '#c084fc', marginBottom: 16, fontWeight: 600 },
  hint: { fontSize: 13, lineHeight: 1.6, textAlign: 'center', maxWidth: 480 },
}
