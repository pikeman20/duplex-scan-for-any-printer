import { defineStore } from 'pinia'
import axios from 'axios'

export const useScansStore = defineStore('scans', {
  state: () => ({
    scans: [] as Array<any>,
    isLoading: false,
    error: null as string | null
  }),

  getters: {
    scanCount: (state: any) => state.scans.length,
    recentScans: (state: any) => state.scans.slice(0, 10)
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
