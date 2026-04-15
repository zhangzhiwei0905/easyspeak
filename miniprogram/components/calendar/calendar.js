Component({
  properties: {
    studyDates: {
      type: Array,
      value: []
    },
    currentMonth: {
      type: String,
      value: ''
    }
  },

  data: {
    year: 0,
    month: 0,
    weekDays: ['一', '二', '三', '四', '五', '六', '日'],
    days: [],
    todayStr: '',
    monthLabel: ''
  },

  observers: {
    'currentMonth': function (val) {
      if (val) {
        const [y, m] = val.split('-').map(Number)
        this._generateCalendar(y, m)
      }
    }
  },

  lifetimes: {
    attached() {
      const now = new Date()
      const y = now.getFullYear()
      const m = now.getMonth() + 1
      const todayStr = this._formatDate(y, now.getMonth(), now.getDate())

      this.setData({ todayStr })

      if (this.data.currentMonth) {
        const [cy, cm] = this.data.currentMonth.split('-').map(Number)
        this._generateCalendar(cy, cm)
      } else {
        this._generateCalendar(y, m)
      }
    }
  },

  methods: {
    _formatDate(year, month, day) {
      const m = String(month + 1).padStart(2, '0')
      const d = String(day).padStart(2, '0')
      return `${year}-${m}-${d}`
    },

    _generateCalendar(year, month) {
      if (!year || !month) return

      const monthNames = [
        '1月', '2月', '3月', '4月', '5月', '6月',
        '7月', '8月', '9月', '10月', '11月', '12月'
      ]

      const days = []
      // First day of month (0=Sun in JS, we need Mon=0)
      const firstDay = new Date(year, month - 1, 1).getDay()
      // Convert: Mon=0, Tue=1, ..., Sun=6
      const startOffset = (firstDay === 0) ? 6 : firstDay - 1

      // Days in this month
      const daysInMonth = new Date(year, month, 0).getDate()

      // Fill leading empty cells
      for (let i = 0; i < startOffset; i++) {
        days.push({ day: 0, dateStr: '', isToday: false, isStudied: false })
      }

      // Fill actual days
      const studySet = new Set(this.data.studyDates || [])
      const todayStr = this.data.todayStr

      for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = this._formatDate(year, month - 1, d)
        days.push({
          day: d,
          dateStr: dateStr,
          isToday: dateStr === todayStr,
          isStudied: studySet.has(dateStr)
        })
      }

      this.setData({
        year: year,
        month: month,
        days: days,
        monthLabel: `${year}年${monthNames[month - 1]}`
      })
    },

    onPrevMonth() {
      let y = this.data.year
      let m = this.data.month - 1
      if (m < 1) { m = 12; y -= 1 }
      this._generateCalendar(y, m)
      this.triggerEvent('monthchange', { year: y, month: m })
    },

    onNextMonth() {
      let y = this.data.year
      let m = this.data.month + 1
      if (m > 12) { m = 1; y += 1 }
      this._generateCalendar(y, m)
      this.triggerEvent('monthchange', { year: y, month: m })
    },

    onDayTap(e) {
      const { dateStr, day } = e.currentTarget.dataset
      if (!day || day === 0) return
      this.triggerEvent('daytap', { dateStr, day })
    }
  }
})
