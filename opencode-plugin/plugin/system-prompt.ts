import type { Plugin } from "@opencode-ai/plugin"
import { readFile } from "fs/promises"
import { execSync } from "child_process"
import { homedir } from "os"

const ENABLED = true
const PROMPT_FILE = `${homedir()}/.config/opencode-openagents/prompts/system-context.md`
const REMINDER_INTERVAL = 6
const MIMIR_REMINDER_TEXT = `\n\n[System Reminder - Message #{{count.next}}]: \n**Mimir Context**: Remember to leverage Mimir tools (search, query, rag_workflow, knowledge_agent) for code exploration. Prefer the indexed knowledge graph over raw searches when available.\n`

interface SessionState {
  messageCount: number
  lastReminderAt: number
  systemContextInjected: boolean
}

const sessionStates = new Map<string, SessionState>()

function getDate(): string {
  return new Date().toISOString().split("T")[0]
}

function getGitBranch(): string {
  try {
    return execSync("git branch --show-current 2>/dev/null", {
      encoding: "utf-8",
      timeout: 3000,
    }).trim()
  } catch {
    return "not-a-git-repo"
  }
}

function getCwd(): string {
  return process.cwd()
}

function getPlatform(): string {
  return process.platform
}

function interpolate(text: string): string {
  return text
    .replace(/\{\{date\}\}/g, getDate())
    .replace(/\{\{git_branch\}\}/g, getGitBranch())
    .replace(/\{\{cwd\}\}/g, getCwd())
    .replace(/\{\{platform\}\}/g, getPlatform())
}

function getSessionState(sessionId: string): SessionState {
  if (!sessionStates.has(sessionId)) {
    sessionStates.set(sessionId, { messageCount: 0, lastReminderAt: 0, systemContextInjected: false })
  }
  return sessionStates.get(sessionId)!
}

function cleanupSession(sessionId: string): void {
  sessionStates.delete(sessionId)
}

function buildMimirReminder(state: SessionState): string {
  return MIMIR_REMINDER_TEXT.replace("{{count.next}}", String(state.messageCount + 1))
}

export const SystemPrompt: Plugin = async ({ client }) => {
  if (!ENABLED) return {}

  let promptContent: string
  try {
    const raw = await readFile(PROMPT_FILE, "utf-8")
    promptContent = interpolate(raw)
    console.log(`[system-prompt] loaded: ${PROMPT_FILE}`)
  } catch (err) {
    console.warn(`[system-prompt] prompt file not found, skipping: ${PROMPT_FILE}`)
    return {}
  }

  return {
    async event(input) {
      const sessionId = input.event.properties?.info?.id

      if (input.event.type === "session.created") {
        if (!sessionId) return
        getSessionState(sessionId)
        return
      }

      if (input.event.type === "message.updated" && sessionId) {
        const state = getSessionState(sessionId)
        state.messageCount++

        if (!state.systemContextInjected) {
          state.systemContextInjected = true
          console.log(`[system-prompt] injecting system context into session: ${sessionId}`)

          await client.session.prompt({
            path: { id: sessionId },
            body: {
              noReply: true,
              parts: [{ type: "text", text: promptContent }],
            },
          })
        }

        const messagesSinceReminder = state.messageCount - state.lastReminderAt
        if (messagesSinceReminder >= REMINDER_INTERVAL) {
          state.lastReminderAt = state.messageCount
          const reminder = buildMimirReminder(state)

          console.log(`[system-prompt] injecting Mimir reminder at message ${state.messageCount}`)

          await client.session.prompt({
            path: { id: sessionId },
            body: {
              noReply: true,
              parts: [{ type: "text", text: reminder }],
            },
          })
        }
        return
      }

      if (input.event.type === "session.idle" || input.event.type === "session.error") {
        if (sessionId) {
          cleanupSession(sessionId)
        }
        return
      }
    },
  }
}
