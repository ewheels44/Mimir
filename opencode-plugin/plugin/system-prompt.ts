import type { Plugin } from "@opencode-ai/plugin"
import { readFile } from "fs/promises"
import { execSync } from "child_process"
import { homedir } from "os"

const ENABLED = true
const PROMPT_FILE = `${homedir()}/.config/opencode-openagents/prompts/system-context.md`
const REMINDER_INTERVAL = 6
const MIMIR_REMINDER_TEXT = `[System Reminder - Message #{{count}}]: **Mimir Tools**: For SDK questions use sdk_cache_get(). For project context use mimir-knowledge_enrich_task() or search(). For complex analysis use rag_workflow() or knowledge_agent(). Load skill "unified-query" for automatic multi-layer search.`

interface SessionState {
  messageCount: number
  lastReminderAt: number
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
    sessionStates.set(sessionId, { messageCount: 0, lastReminderAt: 0 })
  }
  return sessionStates.get(sessionId)!
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

      if (input.event.type === "message.updated" && sessionId) {
        const state = getSessionState(sessionId)
        state.messageCount++
      }
    },

    "experimental.chat.system.transform": async (input, output) => {
      const sessionId = input.sessionID
      if (!sessionId) return

      const state = getSessionState(sessionId)

      // Always inject system context
      output.system.push(promptContent)

      // Inject Mimir reminder every N messages
      const messagesSinceReminder = state.messageCount - state.lastReminderAt
      if (messagesSinceReminder >= REMINDER_INTERVAL) {
        state.lastReminderAt = state.messageCount
        const reminder = MIMIR_REMINDER_TEXT.replace("{{count}}", String(state.messageCount))
        output.system.push(reminder)
        console.log(`[system-prompt] injecting Mimir reminder at message ${state.messageCount}`)
      }
    },
  }
}
