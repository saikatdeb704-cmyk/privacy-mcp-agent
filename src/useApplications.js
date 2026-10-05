import { useState, useCallback } from 'react'

const STORAGE_KEY = 'internship-tracker-apps'

const defaultApps = [
  {
    id: '1',
    company: 'Google',
    role: 'Software Engineering Intern',
    status: 'Applied',
    dateApplied: '2026-09-28',
    deadline: '2026-10-15',
    followUpDate: '2026-10-10',
    contactName: 'Sarah Chen',
    contactEmail: 'sarah.chen@google.com',
    notes: 'Applied through university portal. Team: Cloud Platform. Mentioned interest in distributed systems.',
    resumeLink: '',
    coverLetterLink: '',
    location: 'Mountain View, CA',
    salary: '$45/hr',
    url: 'https://careers.google.com',
  },
  {
    id: '2',
    company: 'Microsoft',
    role: 'Product Management Intern',
    status: 'Interview',
    dateApplied: '2026-09-20',
    deadline: '2026-10-05',
    followUpDate: '2026-10-04',
    contactName: 'James Liu',
    contactEmail: 'j.liu@microsoft.com',
    notes: 'Phone screen completed 9/25. Next: Technical interview on 10/5. Prep: system design + behavioral questions.',
    resumeLink: '',
    coverLetterLink: '',
    location: 'Redmond, WA',
    salary: '$40/hr',
    url: 'https://careers.microsoft.com',
  },
  {
    id: '3',
    company: 'Stripe',
    role: 'Backend Engineering Intern',
    status: 'Offer',
    dateApplied: '2026-09-10',
    deadline: '2026-10-08',
    followUpDate: '',
    contactName: 'Emma Rodriguez',
    contactEmail: 'emma.r@stripe.com',
    notes: 'Received offer 9/30! $55/hr + housing stipend. Need to respond by 10/8. Team: Payments Infrastructure.',
    resumeLink: '',
    coverLetterLink: '',
    location: 'San Francisco, CA',
    salary: '$55/hr',
    url: 'https://stripe.com/jobs',
  },
  {
    id: '4',
    company: 'Amazon',
    role: 'SDE Intern',
    status: 'Rejected',
    dateApplied: '2026-09-05',
    deadline: '',
    followUpDate: '',
    contactName: '',
    contactEmail: '',
    notes: 'Online assessment didn\'t go well. Struggled with the second problem (graph BFS). Reapply next cycle.',
    resumeLink: '',
    coverLetterLink: '',
    location: 'Seattle, WA',
    salary: '',
    url: 'https://amazon.jobs',
  },
  {
    id: '5',
    company: 'Figma',
    role: 'Design Engineering Intern',
    status: 'Saved',
    dateApplied: '',
    deadline: '2026-11-01',
    followUpDate: '',
    contactName: '',
    contactEmail: '',
    notes: 'Applications open Nov 1. Prepare portfolio pieces showcasing design system work.',
    resumeLink: '',
    coverLetterLink: '',
    location: 'San Francisco, CA',
    salary: '',
    url: 'https://figma.com/careers',
  },
]

function loadApps() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return JSON.parse(stored)
    }
  } catch (e) {
    console.error('Failed to load apps from storage', e)
  }
  return defaultApps
}

function saveApps(apps) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(apps))
  } catch (e) {
    console.error('Failed to save apps to storage', e)
  }
}

export function useApplications() {
  const [applications, setApplications] = useState(loadApps)

  const updateApps = useCallback((updater) => {
    setApplications((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      saveApps(next)
      return next
    })
  }, [])

  const addApplication = useCallback((app) => {
    const newApp = {
      ...app,
      id: Date.now().toString() + Math.random().toString(36).slice(2),
    }
    updateApps((prev) => [newApp, ...prev])
    return newApp
  }, [updateApps])

  const updateApplication = useCallback((id, updates) => {
    updateApps((prev) =>
      prev.map((app) => (app.id === id ? { ...app, ...updates } : app))
    )
  }, [updateApps])

  const deleteApplication = useCallback((id) => {
    updateApps((prev) => prev.filter((app) => app.id !== id))
  }, [updateApps])

  const getStats = useCallback(() => {
    const stats = {
      total: applications.length,
      applied: 0,
      interview: 0,
      offer: 0,
      rejected: 0,
      saved: 0,
    }
    for (const app of applications) {
      const key = app.status.toLowerCase()
      if (key in stats) stats[key]++
    }
    return stats
  }, [applications])

  const getReminders = useCallback(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const reminders = []

    for (const app of applications) {
      if (app.status === 'Rejected') continue

      if (app.deadline) {
        const deadlineDate = new Date(app.deadline)
        deadlineDate.setHours(0, 0, 0, 0)
        const daysUntil = Math.ceil((deadlineDate - today) / (1000 * 60 * 60 * 24))
        if (daysUntil >= 0 && daysUntil <= 7) {
          reminders.push({
            app,
            type: 'deadline',
            daysUntil,
            urgent: daysUntil <= 2,
            label: daysUntil === 0 ? 'Deadline TODAY' : `Deadline in ${daysUntil} day${daysUntil > 1 ? 's' : ''}`,
          })
        }
      }

      if (app.followUpDate) {
        const followUp = new Date(app.followUpDate)
        followUp.setHours(0, 0, 0, 0)
        const daysUntil = Math.ceil((followUp - today) / (1000 * 60 * 60 * 24))
        if (daysUntil >= 0 && daysUntil <= 3) {
          reminders.push({
            app,
            type: 'followUp',
            daysUntil,
            urgent: daysUntil === 0,
            label: daysUntil === 0 ? 'Follow up TODAY' : `Follow up in ${daysUntil} day${daysUntil > 1 ? 's' : ''}`,
          })
        }
      }
    }

    reminders.sort((a, b) => a.daysUntil - b.daysUntil)
    return reminders
  }, [applications])

  return {
    applications,
    addApplication,
    updateApplication,
    deleteApplication,
    getStats,
    getReminders,
  }
}
