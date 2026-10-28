export function searchPapers(papers, query) {
  const normalizedQuery = query.trim().toLocaleLowerCase()
  if (!normalizedQuery) return papers

  return papers.filter((paper) => {
    const metadata = paper.metadata || {}
    const analysis = paper.analysis || {}
    const searchableText = [
      paper.filename,
      metadata.title,
      metadata.year,
      ...(metadata.authors || []),
      ...(metadata.keywords || []),
      ...(analysis.methodology?.method_terms || []),
      ...(analysis.claim_records || []).map((claim) => claim.text),
      ...(analysis.research_gaps || []),
    ].join(' ').toLocaleLowerCase()
    return searchableText.includes(normalizedQuery)
  })
}

export function filterPapers(papers, filters) {
  return papers.filter((paper) => {
    const metadata = paper.metadata || {}
    const analysis = paper.analysis || {}
    if (filters.year !== 'all' && String(metadata.year ?? '') !== filters.year) return false
    if (filters.topic !== 'all' && !(metadata.keywords || []).includes(filters.topic)) return false
    if (
      filters.method !== 'all'
      && !(analysis.methodology?.method_terms || []).includes(filters.method)
    ) return false
    if (
      filters.evidence !== 'all'
      && analysis.evidence_score?.label !== filters.evidence
    ) return false
    return true
  })
}

export function filterComparisons(comparisons, relationshipType) {
  if (relationshipType === 'all') return comparisons
  return comparisons.filter((comparison) => comparison.status === relationshipType)
}

export function createResearchReport(
  paper,
  uploadedPapers,
  comparison,
  researchGaps,
  generatedAt = new Date().toISOString(),
) {
  const relatedIds = new Set([
    paper.paper_id,
    ...(comparison?.paper_ids || []),
    ...(researchGaps?.paper_ids || []),
  ])
  return {
    report_version: 1,
    generated_at: generatedAt,
    papers: uploadedPapers.filter((entry) => relatedIds.has(entry.paper_id)),
    comparison: comparison || null,
    research_gap_review: researchGaps || null,
    uncertainty_notes: [
      paper.analysis?.evidence_score?.limitations,
      ...(comparison?.limitations || []),
      ...(researchGaps?.scoring?.limitations || []),
    ].filter(Boolean),
  }
}

export function researchReportFileName(paper) {
  return (paper.metadata?.title || paper.filename || 'research-analysis')
    .replace(/[<>:"/\\|?*]/g, '-')
    .split('')
    .map((character) => character.charCodeAt(0) < 32 ? '-' : character)
    .join('')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 80) || 'research-analysis'
}
