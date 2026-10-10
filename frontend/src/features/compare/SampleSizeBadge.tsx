import { Badge } from '@/components/ui/badge'

export const MIN_SAMPLE = 30

export function SampleSizeBadge({ plays, games }: { plays: number; games: number }) {
  const small = plays < MIN_SAMPLE
  return (
    <Badge
      variant={small ? 'destructive' : 'secondary'}
      title={small ? `Fewer than ${MIN_SAMPLE} plays: treat these numbers with caution` : undefined}
    >
      {plays.toLocaleString()} plays · {games} {games === 1 ? 'game' : 'games'}
    </Badge>
  )
}
