import assert from 'node:assert/strict'
import test from 'node:test'
import {
  createResearchReport,
  filterComparisons,
  filterPapers,
  researchReportFileName,
  searchPapers,
} from '../src/researchReport.js'

const papers = [
  {
    paper_id: 'paper-a',
    filename: 'study-a.pdf',
    metadata: {
      title: 'Climate Study',
      year: 2022,
      authors: ['A. Researcher'],
      keywords: ['climate'],
    },
    analysis: {
      methodology: { method_terms: ['survey'] },
      claim_records: [{ text: 'Results show improvement.' }],
      research_gaps: ['Future work should evaluate outcomes.'],
      evidence_score: { label: 'moderate' },
    },
  },
  {
    paper_id: 'paper-b',
    filename: 'study-b.pdf',
    metadata: {
      title: 'Health Study',
      year: 2024,
      authors: ['B. Researcher'],
      keywords: ['health'],
    },
    analysis: {
      methodology: { method_terms: ['experiment'] },
      evidence_score: { label: 'high' },
    },
  },
]

test('search matches supported session metadata and extracted analysis fields', () => {
  assert.deepEqual(searchPapers(papers, '  2024 '), [papers[1]])
  assert.deepEqual(searchPapers(papers, 'SURVEY'), [papers[0]])
  assert.deepEqual(searchPapers(papers, 'climate'), [papers[0]])
  assert.deepEqual(searchPapers(papers, 'future work'), [papers[0]])
  assert.deepEqual(searchPapers(papers, 'missing'), [])
  assert.deepEqual(searchPapers(papers, ''), papers)
})

test('paper filters combine actual year, keyword, method, and evidence labels', () => {
  assert.deepEqual(filterPapers(papers, { year: '2022', topic: 'all', method: 'all', evidence: 'all' }), [papers[0]])
  assert.deepEqual(filterPapers(papers, { year: 'all', topic: 'health', method: 'experiment', evidence: 'high' }), [papers[1]])
  assert.deepEqual(filterPapers(papers, { year: '2024', topic: 'climate', method: 'all', evidence: 'all' }), [])
})

test('relationship filter returns all or only the selected relationship', () => {
  const comparisons = [
    { status: 'supporting' },
    { status: 'potential_conflict' },
  ]

  assert.deepEqual(filterComparisons(comparisons, 'all'), comparisons)
  assert.deepEqual(
    filterComparisons(comparisons, 'potential_conflict'),
    [comparisons[1]],
  )
  assert.deepEqual(filterComparisons(comparisons, 'missing'), [])
})

test('report includes source papers, returned analysis, and uncertainty notes', () => {
  const paper = {
    ...papers[0],
    analysis: {
      ...papers[0].analysis,
      evidence_score: { limitations: 'Heuristic, not calibrated.' },
    },
  }
  const comparison = {
    paper_ids: ['paper-a', 'paper-b'],
    limitations: ['Lexical screening only.'],
  }
  const gaps = {
    paper_ids: ['paper-a', 'paper-b'],
    scoring: { limitations: ['Selected papers only.'] },
  }

  const report = createResearchReport(
    paper,
    papers,
    comparison,
    gaps,
    '2026-01-01T00:00:00.000Z',
  )

  assert.deepEqual(report.papers.map((entry) => entry.paper_id), ['paper-a', 'paper-b'])
  assert.equal(report.generated_at, '2026-01-01T00:00:00.000Z')
  assert.equal(report.comparison, comparison)
  assert.equal(report.research_gap_review, gaps)
  assert.deepEqual(report.uncertainty_notes, [
    'Heuristic, not calibrated.',
    'Lexical screening only.',
    'Selected papers only.',
  ])
})

test('report supports missing comparison data and sanitizes the download name', () => {
  const paper = {
    ...papers[0],
    metadata: { ...papers[0].metadata, title: 'Unsafe:/ title?\u0001' },
  }

  assert.equal(createResearchReport(paper, [paper], null, null).comparison, null)
  assert.equal(researchReportFileName(paper), 'Unsafe---title--')
})
