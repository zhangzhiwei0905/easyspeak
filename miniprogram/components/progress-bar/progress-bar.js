Component({
  properties: {
    current: {
      type: Number,
      value: 0
    },
    total: {
      type: Number,
      value: 100
    },
    color: {
      type: String,
      value: '#667eea'
    },
    height: {
      type: Number,
      value: 16
    }
  },

  data: {
    percentage: 0,
    displayPercentage: 0,
    barWidth: '0%'
  },

  observers: {
    'current, total': function (current, total) {
      const safeTotal = Math.max(total, 1)
      const safeCurrent = Math.max(0, Math.min(current, safeTotal))
      const pct = Math.round((safeCurrent / safeTotal) * 100)
      this.setData({
        percentage: pct,
        barWidth: pct + '%'
      })

      // Animate the percentage text
      this._animatePercentage(pct)
    }
  },

  lifetimes: {
    attached() {
      const safeTotal = Math.max(this.data.total, 1)
      const safeCurrent = Math.max(0, Math.min(this.data.current, safeTotal))
      const pct = Math.round((safeCurrent / safeTotal) * 100)
      this.setData({
        percentage: pct,
        displayPercentage: pct,
        barWidth: pct + '%'
      })
    }
  },

  methods: {
    _animatePercentage(targetPct) {
      const startPct = this.data.displayPercentage
      const diff = targetPct - startPct
      if (Math.abs(diff) < 1) {
        this.setData({ displayPercentage: targetPct })
        return
      }

      const duration = 500
      const startTime = Date.now()
      const animate = () => {
        const elapsed = Date.now() - startTime
        const progress = Math.min(elapsed / duration, 1)
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3)
        const current = Math.round(startPct + diff * eased)
        this.setData({ displayPercentage: current })

        if (progress < 1) {
          setTimeout(animate, 16)
        } else {
          this.setData({ displayPercentage: targetPct })
        }
      }
      animate()
    }
  }
})
