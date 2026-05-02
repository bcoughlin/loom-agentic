/**
 * Scorecards page — list of agent charters with rolling averages,
 * recent assessments, and links to per-agent detail.
 *
 * Placeholder. Wired in plan_2 once the scorecard module's charter
 * loader + score store + post-hoc runner ship. This page is a
 * presentation surface over /api/charters and /api/scores.
 */
export default function Scorecards() {
  return (
    <div style={styles.empty}>
      <div style={styles.title}>Scorecards</div>
      <div style={styles.hint}>
        Per-agent charter views with rolling averages.
        <br/>
        Wired in plan_2 once charter loader + score store ship,
        then plan_3 step 10.
      </div>
    </div>
  )
}

const styles = {
  empty: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, color: '#888', fontFamily: 'monospace', padding: 40 },
  title: { fontSize: 20, color: '#c084fc', marginBottom: 16, fontWeight: 600 },
  hint: { fontSize: 13, lineHeight: 1.6, textAlign: 'center', maxWidth: 480 },
}
