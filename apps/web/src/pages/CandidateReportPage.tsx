import { useParams } from 'react-router-dom'
import { CandidateProfile } from '../components/candidates/CandidateProfile'

export default function CandidateReportPage() {
  const { id } = useParams<{ id: string }>()
  if (!id) return null
  return <CandidateProfile candidateId={id} mode="report" />
}
