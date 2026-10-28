import { useState } from 'react'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  createResearchReport,
  filterComparisons,
  filterPapers,
  researchReportFileName,
  searchPapers,
} from './researchReport'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001'

function App() {
  const [file, setFile] = useState(null)
  const [paper, setPaper] = useState(null)
  const [uploadedPapers, setUploadedPapers] = useState([])
  const [selectedPaperIds, setSelectedPaperIds] = useState([])
  const [paperSearch, setPaperSearch] = useState('')
  const [paperFilters, setPaperFilters] = useState({
    year: 'all',
    topic: 'all',
    method: 'all',
    evidence: 'all',
  })
  const [comparisonTypeFilter, setComparisonTypeFilter] = useState('all')
  const [comparison, setComparison] = useState(null)
  const [comparisonError, setComparisonError] = useState('')
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const [researchGaps, setResearchGaps] = useState(null)
  const [researchGapError, setResearchGapError] = useState('')
  const [researchGapLoading, setResearchGapLoading] = useState(false)
  const [status, setStatus] = useState('Ready for a paper')
  const [loading, setLoading] = useState(false)

  async function uploadPaper(event) {
    event.preventDefault()
    if (!file) return
    setLoading(true)
    setStatus('Reading paper...')
    const formData = new FormData()
    formData.append('file', file)
    try {
      const response = await fetch(`${API_URL}/papers/upload`, { method: 'POST', body: formData })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || 'Upload failed')
      setPaper(result)
      setUploadedPapers((existing) => [...existing, result])
      setSelectedPaperIds((existing) => [...existing, result.paper_id].slice(-10))
      setComparison(null)
      setComparisonTypeFilter('all')
      setComparisonError('')
      setResearchGaps(null)
      setResearchGapError('')
      setStatus('Analysis complete')
    } catch (error) {
      setStatus(error.message)
    } finally {
      setLoading(false)
    }
  }

  async function compareSelectedPapers() {
    setComparisonLoading(true)
    setComparisonError('')
    try {
      const response = await fetch(`${API_URL}/papers/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper_ids: selectedPaperIds }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) {
        const detail = typeof result.detail === 'string'
          ? result.detail
          : result.detail?.message || 'Paper comparison failed'
        throw new Error(detail)
      }
      setComparison(result)
      setComparisonTypeFilter('all')
    } catch (error) {
      setComparisonError(error.message)
      setComparison(null)
    } finally {
      setComparisonLoading(false)
    }
  }

  async function findResearchGaps() {
    setResearchGapLoading(true)
    setResearchGapError('')
    try {
      const response = await fetch(`${API_URL}/papers/gaps`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper_ids: selectedPaperIds }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) {
        const detail = typeof result.detail === 'string'
          ? result.detail
          : result.detail?.message || 'Research-gap analysis failed'
        throw new Error(detail)
      }
      setResearchGaps(result)
    } catch (error) {
      setResearchGapError(error.message)
      setResearchGaps(null)
    } finally {
      setResearchGapLoading(false)
    }
  }

  function togglePaperSelection(paperId) {
    setSelectedPaperIds((selected) => selected.includes(paperId)
      ? selected.filter((id) => id !== paperId)
      : [...selected, paperId])
    setComparison(null)
    setResearchGaps(null)
    setComparisonTypeFilter('all')
  }

  function downloadResearchReport() {
    if (!paper) return
    const report = createResearchReport(
      paper,
      uploadedPapers,
      comparison,
      researchGaps,
    )
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }),
    )
    const link = document.createElement('a')
    link.href = url
    link.download = `${researchReportFileName(paper)}.json`
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const paperFilterOptions = {
    year: [...new Set(uploadedPapers
      .map((entry) => entry.metadata?.year)
      .filter((value) => value !== null && value !== undefined && value !== '')
      .map(String))].sort(),
    topic: [...new Set(uploadedPapers.flatMap((entry) => entry.metadata?.keywords || []))].sort(),
    method: [...new Set(uploadedPapers.flatMap((entry) => entry.analysis?.methodology?.method_terms || []))].sort(),
    evidence: [...new Set(uploadedPapers
      .map((entry) => entry.analysis?.evidence_score?.label)
      .filter(Boolean))].sort(),
  }
  const filteredUploadedPapers = filterPapers(
    searchPapers(uploadedPapers, paperSearch),
    paperFilters,
  )
  const visibleComparisons = filterComparisons(
    comparison?.comparisons || [],
    comparisonTypeFilter,
  )

  const sectionData = paper ? Object.entries(paper.sections).map(([name, value]) => ({ name: name.slice(0, 13), words: value.split(/\s+/).filter(Boolean).length })) : []
  const analysis = paper?.analysis

  return (
    <main>
      <header className="topbar"><div className="mark">LI</div><span>Literature Intelligence</span><span className="status"><i /> {status}</span></header>
      <section className="intro"><p className="eyebrow">ACADEMIC EVIDENCE DESK</p><h1>Turn a paper into a point of view.</h1><p className="lede">Upload one study to surface its structure, method, evidence, and open questions.</p></section>
      <form className="dropzone" onSubmit={uploadPaper}>
        <label htmlFor="paper-file"><span className="upload-icon">↑</span><strong>{file ? file.name : 'Choose an academic PDF'}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB selected` : 'PDF files up to 50 MB'}</small></label>
        <input id="paper-file" type="file" accept="application/pdf,.pdf" onChange={(event) => setFile(event.target.files[0])} />
        <button type="submit" disabled={!file || loading}>{loading ? 'Analysing...' : 'Analyse paper →'}</button>
      </form>
      <section className="comparison-section">
        <div className="panel-title"><h3>Compare uploaded papers</h3><span>{uploadedPapers.length} in this session</span></div>
        {uploadedPapers.length > 0 && (
          <label className="paper-search">
            Search this session by title, author, year, topic, method, or claim
            <input
              type="search"
              value={paperSearch}
              onChange={(event) => setPaperSearch(event.target.value)}
              placeholder="Search uploaded papers"
            />
          </label>
        )}
        {uploadedPapers.length > 0 && (
          <div className="paper-filters">
            {Object.entries({
              year: 'Year',
              topic: 'Topic',
              method: 'Method',
              evidence: 'Evidence strength',
            }).map(([filterKey, label]) => (
              <label key={filterKey}>
                {label}
                <select
                  aria-label={`Filter by ${label.toLowerCase()}`}
                  value={paperFilters[filterKey]}
                  onChange={(event) => setPaperFilters((current) => ({
                    ...current,
                    [filterKey]: event.target.value,
                  }))}
                >
                  <option value="all">All</option>
                  {paperFilterOptions[filterKey].map((value) => (
                    <option value={value} key={value}>{value}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        )}
        {!uploadedPapers.length
          ? <p className="comparison-empty">Upload papers to compare their reported evidence.</p>
          : <>
            <div className="paper-selector">
              {filteredUploadedPapers.map((uploadedPaper) => (
                <label className="paper-option" key={uploadedPaper.paper_id}>
                  <input
                    type="checkbox"
                    checked={selectedPaperIds.includes(uploadedPaper.paper_id)}
                    disabled={!selectedPaperIds.includes(uploadedPaper.paper_id) && selectedPaperIds.length >= 10}
                    onChange={() => togglePaperSelection(uploadedPaper.paper_id)}
                  />
                  <span>{uploadedPaper.metadata.title || uploadedPaper.filename}</span>
                </label>
              ))}
            </div>
            {filteredUploadedPapers.length === 0 && <p className="comparison-empty">No uploaded papers match this search.</p>}
            <button
              className="compare-button"
              type="button"
              disabled={selectedPaperIds.length < 2 || comparisonLoading}
              onClick={compareSelectedPapers}
            >
              {comparisonLoading ? 'Comparing...' : `Compare ${selectedPaperIds.length} papers`}
            </button>
            <button
              className="compare-button secondary"
              type="button"
              disabled={!selectedPaperIds.length || researchGapLoading}
              onClick={findResearchGaps}
            >
              {researchGapLoading ? 'Reviewing evidence...' : 'Find cited gaps'}
            </button>
            {comparisonError && <p className="comparison-error" role="alert">{comparisonError}</p>}
            {researchGapError && <p className="comparison-error" role="alert">{researchGapError}</p>}
            {comparison?.comparisons?.length > 0 && (
              <div className="comparison-results">
                {comparison.comparisons.length > 0 && (
                  <label className="relationship-filter">
                    Relationship type
                    <select value={comparisonTypeFilter} onChange={(event) => setComparisonTypeFilter(event.target.value)}>
                      <option value="all">All results</option>
                      {[...new Set(comparison.comparisons.map((item) => item.status))].map((statusValue) => (
                        <option value={statusValue} key={statusValue}>{statusValue.replaceAll('_', ' ')}</option>
                      ))}
                    </select>
                  </label>
                )}
                {visibleComparisons.map((item) => (
                  <article className="comparison-card" key={`${item.paper_ids.join(':')}:${item.status}`}>
                    <div className="panel-title">
                      <h4>{item.paper_ids.map((id) => comparison.papers.find((entry) => entry.paper_id === id)?.title || id).join(' ↔ ')}</h4>
                      <span>{item.status.replaceAll('_', ' ')}</span>
                    </div>
                    <p>{item.explanation}</p>
                    {item.claim_comparisons.map((claimPair, index) => (
                      <div className="claim-pair" key={`${item.paper_ids.join(':')}-${index}`}>
                        <strong>{claimPair.status.replaceAll('_', ' ')}</strong>
                        {claimPair.evidence.map((claim, claimIndex) => (
                          <blockquote key={`${claim.paper_id}-${claimIndex}`}>
                            <span>{comparison.papers.find((entry) => entry.paper_id === claim.paper_id)?.title || claim.paper_id}
                              {[claim.section, claim.page ? `page ${claim.page}` : null].filter(Boolean).join(' · ') && ` · ${[claim.section, claim.page ? `page ${claim.page}` : null].filter(Boolean).join(' · ')}`}
                            </span>
                            {claim.text}
                          </blockquote>
                        ))}
                      </div>
                    ))}
                  </article>
                ))}
              </div>
            )}
            {comparison && !visibleComparisons.length && <p className="comparison-empty">{comparison.comparisons.length ? 'No pairwise comparisons match this relationship filter.' : 'No pairwise comparisons are available.'}</p>}
            {comparison?.limitations?.length > 0 && <p className="comparison-limitation">{comparison.limitations.join(' ')}</p>}
            {comparison?.summary_statistics && (
              <section className="cross-paper-statistics">
                <h4>Cross-paper summary</h4>
                <p>{comparison.summary_statistics.paper_count} selected papers · publication year available for {comparison.summary_statistics.publication_years.available_count}</p>
                <div className="cross-paper-scores">
                  <strong>Evidence Stability Score · heuristic</strong>
                  {comparison.summary_statistics.evidence_stability_scores.available_count
                    ? <>
                      <span>Average {comparison.summary_statistics.evidence_stability_scores.average} · range {comparison.summary_statistics.evidence_stability_scores.minimum}–{comparison.summary_statistics.evidence_stability_scores.maximum}</span>
                      <ul>{comparison.summary_statistics.evidence_stability_scores.values.map((score) => <li key={score.paper_id}>{comparison.papers.find((entry) => entry.paper_id === score.paper_id)?.title || score.paper_id}: {score.score}{score.label ? ` · ${score.label}` : ''}</li>)}</ul>
                    </>
                    : <span>No evidence scores are available for the selected papers.</span>}
                </div>
                <div className="cross-paper-methods">
                  <strong>Reported method terms</strong>
                  {comparison.summary_statistics.method_term_counts.length
                    ? comparison.summary_statistics.method_term_counts.map((method) => <span key={method.term}>{method.term} · {method.paper_count}</span>)
                    : <span>No method terms were extracted.</span>}
                </div>
              </section>
            )}
            {researchGaps && (
              <div className="comparison-results">
                <div className="panel-title"><h3>Research-gap signals</h3><span>{researchGaps.gaps.length} found</span></div>
                {researchGaps.gaps.length
                  ? researchGaps.gaps.map((gap, index) => (
                    <article className="comparison-card" key={`${gap.type}-${index}`}>
                      <div className="panel-title">
                        <h4>{gap.type.replaceAll('_', ' ')}</h4>
                        <span>Opportunity score {gap.opportunity_score} · heuristic</span>
                      </div>
                      <p>{gap.statement}</p>
                      <p className="gap-explanation">{gap.identification_reason}</p>
                      <p>{gap.score_factors.map((factor) => `${factor.name.replaceAll('_', ' ')}: +${factor.points} — ${factor.reason}`).join(' ')}</p>
                      {gap.evidence.map((source, sourceIndex) => (
                        <blockquote className="gap-source" key={`${source.paper_id}-${sourceIndex}`}>
                          <span>{researchGaps.paper_ids.includes(source.paper_id) ? uploadedPapers.find((entry) => entry.paper_id === source.paper_id)?.metadata.title || source.paper_id : source.paper_id}
                            {[source.section, source.page ? `page ${source.page}` : null].filter(Boolean).length > 0 && ` · ${[source.section, source.page ? `page ${source.page}` : null].filter(Boolean).join(' · ')}`}
                          </span>
                          {source.text}
                        </blockquote>
                      ))}
                    </article>
                  ))
                  : <p className="comparison-empty">No explicit gap statements or conflicting-claim screening signals were found in these papers. Absence from this selection is not evidence that a research gap does not exist.</p>}
                <p className="comparison-limitation">{researchGaps.scoring.limitations.join(' ')}</p>
              </div>
            )}
          </>}
      </section>
      {paper && <>
        <section className="paper-head"><div><p className="eyebrow">CURRENT PAPER · {paper.metadata.year || 'YEAR UNKNOWN'}</p><h2>{paper.metadata.title || paper.filename}</h2><p>{paper.metadata.authors.join(' · ') || 'Authors not detected'} {paper.metadata.doi && <span className="doi">DOI {paper.metadata.doi}</span>}</p><button className="compare-button secondary export-button" type="button" onClick={downloadResearchReport}>Export analysis report (.json)</button></div><div className="score"><span>{analysis.evidence_score.score}</span><small>Evidence Stability<br />{analysis.evidence_score.label} · heuristic</small></div>{analysis.evidence_score.factors && <details className="score-explanation"><summary>Score factors</summary><p>{analysis.evidence_score.normalization?.formula || 'Heuristic score factors'}; result {analysis.evidence_score.normalization?.applied_score ?? analysis.evidence_score.score} / 100.</p><ul>{analysis.evidence_score.factors.map((factor) => <li key={factor.name}><strong>{factor.applied ? `+${factor.points}` : '+0'} · {factor.name.replaceAll('_', ' ')}</strong><span>{factor.reason}</span></li>)}</ul><p>{analysis.evidence_score.limitations}</p></details>}</section>
        <section className="grid">
          <article className="panel chart-panel"><div className="panel-title"><h3>Section footprint</h3><span>{Object.keys(paper.sections).length} detected</span></div><ResponsiveContainer width="100%" height={220}><BarChart data={sectionData}><XAxis dataKey="name" tick={{ fill: '#68736d', fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis hide /><Tooltip cursor={{ fill: '#f2eee5' }} /><Bar dataKey="words" fill="#da5c3e" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></article>
          <article className="panel"><div className="panel-title"><h3>Methodology</h3><span>{analysis.methodology.available ? 'Found' : 'Not detected'}</span></div><p className="summary">{analysis.methodology.summary || 'No methodology section was detected.'}</p><div className="tags">{analysis.methodology.method_terms.map((term) => <span key={term}>{term}</span>)}</div></article>
          <article className="panel"><div className="panel-title"><h3>Claims</h3><span>{analysis.claim_records?.length || analysis.claims.length}</span></div><ul>{analysis.claim_records?.length ? analysis.claim_records.slice(0, 4).map((claim, index) => <li key={`${claim.paper_id ?? paper.paper_id}-${index}`}><span className="claim-category">{claim.category}</span>{claim.text}<small className="claim-explanation">{claim.classification_reason}</small><small className="claim-source">{[claim.section, claim.page ? `page ${claim.page}` : null].filter(Boolean).join(' · ') || 'Source location unavailable'}</small></li>) : analysis.claims.slice(0, 4).map((claim) => <li key={claim}>{claim}</li>)}</ul></article>
          <article className="panel"><div className="panel-title"><h3>Research gaps</h3><span>{analysis.research_gaps.length}</span></div><ul>{analysis.research_gaps.slice(0, 4).map((gap) => <li key={gap}>{gap}</li>)}</ul></article>
          <article className="panel full"><div className="panel-title"><h3>Statistics found</h3><span>{analysis.statistics.length} signals</span></div><div className="stat-list">{analysis.statistics.slice(0, 6).map((stat) => <p key={stat}>{stat}</p>)}</div></article>
        </section>
      </>}
    </main>
  )
}

export default App
