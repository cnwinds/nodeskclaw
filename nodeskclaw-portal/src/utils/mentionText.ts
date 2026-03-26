import type { AgentBrief, WorkspaceMemberInfo } from '@/stores/workspace'

const MENTION_TOKEN_RE = /@(?:(agent|human):)?([a-f0-9-]{36}|__all__)\b/gi

export function replaceMentionTokens(
  raw: string,
  agents: AgentBrief[],
  members: WorkspaceMemberInfo[],
  everyoneLabel: string,
): string {
  if (!raw) return raw
  const agentNameById = new Map(
    agents.map(a => [a.instance_id.toLowerCase(), a.display_name || a.name]),
  )
  const humanNameById = new Map(
    members.map(m => [m.user_id.toLowerCase(), m.user_name]),
  )

  return raw.replace(MENTION_TOKEN_RE, (full, mentionType: string | undefined, rawId: string) => {
    const mentionId = rawId.toLowerCase()
    if (mentionId === '__all__') return `@${everyoneLabel}`

    let name: string | undefined
    if (mentionType === 'agent') name = agentNameById.get(mentionId)
    else if (mentionType === 'human') name = humanNameById.get(mentionId)
    else name = agentNameById.get(mentionId) || humanNameById.get(mentionId)

    return name ? `@${name}` : full
  })
}
