Component({
  properties: {
    calendarData: {
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
    },
    'calendarData': function () {
      if (this.data.year && this.data.month) {
        this._generateCalendar(this.data.year, this.data.month)
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

      // Build lookup from calendarData array
      const dataMap = {}
      const items = this.data.calendarData || []
      for (let i = 0; i < items.length; i++) {
        if (items[i] && items[i].date) {
          dataMap[items[i].date] = items[i]
        }
      }

      // Fill leading empty cells
      for (let i = 0; i < startOffset; i++) {
        days.push({ day: 0, dateStr: '', isToday: false, className: 'calendar__day--empty', status: 'empty' })
      }

      // Fill actual days
      const todayStr = this.data.todayStr

      for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = this._formatDate(year, month - 1, d)
        const info = dataMap[dateStr] || null
        const isToday = dateStr === todayStr
        const reviewed = info ? (info.reviewed_count || info.reviewed || 0) : 0

        // Determine status
        var status = 'none' // no content
        if (info && info.has_content) {
          if (info.learned) {
            if (info.first_pass_rate !== null && info.first_pass_rate !== undefined) {
              if (info.first_pass_rate >= 80) {
                status = 'excellent'
              } else if (info.first_pass_rate < 50) {
                status = 'poor'
              } else {
                status = 'studied'
              }
            } else {
              status = 'studied'
            }
          } else {
            status = 'unlearned'
          }
        } else if (reviewed > 0) {
          status = 'reviewed'
        }

        // Build className string
        var className = ''
        if (isToday) className += ' calendar__day--today'
        if (status === 'unlearned') className += ' calendar__day--unlearned'
        if (status === 'studied') className += ' calendar__day--studied'
        if (status === 'excellent') className += ' calendar__day--excellent'
        if (status === 'poor') className += ' calendar__day--poor'
        if (status === 'reviewed') className += ' calendar__day--reviewed'
        if (d === 0) className += ' calendar__day--empty'

        days.push({
          day: d,
          dateStr: dateStr,
          isToday: isToday,
          className: className,
          status: status,
          reviewed: reviewed,
          reviewedCount: reviewed,
          // Pass through detail data for popup
          themeZh: info ? info.theme_zh || '' : '',
          phraseCount: info ? info.phrase_count || 0 : 0,
          wordCount: info ? info.word_count || 0 : 0,
          firstPassRate: info ? info.first_pass_rate : null,
          avgMastery: info ? info.avg_mastery || 0 : 0,
          reviewPhraseCount: info ? info.review_phrase_count || 0 : 0,
          reviewWordCount: info ? info.review_word_count || 0 : 0,
          forgotCount: info ? info.forgot_count || 0 : 0,
          fuzzyCount: info ? info.fuzzy_count || 0 : 0,
          rememberedCount: info ? info.remembered_count || 0 : 0,
          solidCount: info ? info.solid_count || 0 : 0
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
      const { datestr, day } = e.currentTarget.dataset
      if (!day || day === 0) return
      // Find day data
      const days = this.data.days
      var dayData = null
      for (var i = 0; i < days.length; i++) {
        if (days[i].dateStr === datestr) {
          dayData = days[i]
          break
        }
      }
      this.triggerEvent('daytap', { dateStr: datestr, day: day, dayData: dayData })
    }
  }
})
