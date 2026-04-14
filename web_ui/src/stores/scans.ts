import { defineStore } from 'pinia'
import axios from 'axios'

export interface BotStatus {
  enabled: boolean
  connected: boolean
  pending_sessions: number
  authorized_users: number
  message: string
}

export interface SessionStatus {
  current_session_id: string | null
  state: string
  mode: string
  image_count: number
  timeout_seconds: number
  message: string
}

export const useScansStore = defineStore('scans', {
  state: () => ({
    scans: [] as Array<any>,
    isLoading: false,
    error: null as string | null,
    botStatus: null as BotStatus | null,
    sessionStatus: null as SessionStatus | null
  }),

  getters: {
    scanCount: (state: any) => state.scans.length,
    recentScans: (state: any) => state.scans.slice(0, 10),
    isBotEnabled: (state: any) => state.botStatus?.enabled ?? false,
    isBotConnected: (state: any) => state.botStatus?.connected ?? false,
    hasPendingSession: (state: any) => state.sessionStatus?.state === 'WAIT_CONFIRM'
  },

  actions: {
    async fetchScans() {
      this.isLoading = true
      this.error = null

      try {
        const response = await axios.get('/api/scans')
        this.scans = response.data.scans
      } catch (error: any) {
        this.error = error.message
        console.error('Failed to fetch scans:', error)
      } finally {
        this.isLoading = false
      }
    },

    async fetchBotStatus() {
      try {
        const response = await axios.get('/api/bot/status')
        this.botStatus = response.data
      } catch (error) {
        console.error('Failed to fetch bot status:', error)
      }
    },

    async fetchSessionStatus() {
      try {
        const response = await axios.get('/api/session/status')
        this.sessionStatus = response.data
      } catch (error) {
        console.error('Failed to fetch session status:', error)
      }
    },

    async deleteScan(filename: string) {
      try {
        await axios.delete(`/api/scan/${filename}`)
        this.scans = this.scans.filter((scan: any) => scan.filename !== filename)
      } catch (error) {
        console.error('Failed to delete scan:', error)
        throw error
      }
    },

    getScanByFilename(filename: string) {
      return this.scans.find((scan: any) => scan.filename === filename)
    }
  }
})
