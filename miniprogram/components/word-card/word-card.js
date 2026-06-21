Component({
  properties: {
    word: { type: String, value: '' },
    phonetic: { type: String, value: '' },
    partOfSpeech: { type: String, value: '' },
    meaning: { type: String, value: '' },
    example: { type: String, value: '' },
    usageNote: { type: String, value: '' },
    contextMeanings: { type: Array, value: [] }
  },

  data: {
    expanded: false,
    displayContextMeanings: [],
    isPlaying: false,
    playingType: '' // 'us' | 'uk' | ''
  },

  lifetimes: {
    attached() {
      this._audioCtx = wx.createInnerAudioContext()
      this._audioCtx.onEnded(() => {
        this.setData({ isPlaying: false, playingType: '' })
      })
      this._audioCtx.onError(() => {
        this.setData({ isPlaying: false, playingType: '' })
        wx.showToast({ title: '发音加载失败', icon: 'none', duration: 1500 })
      })
    },
    detached() {
      if (this._audioCtx) {
        this._audioCtx.destroy()
        this._audioCtx = null
      }
    }
  },

  observers: {
    contextMeanings(value) {
      this.setData({ displayContextMeanings: this.normalizeContextMeanings(value) })
    }
  },

  methods: {
    onTapCard() {
      const next = !this.data.expanded
      this.setData({ expanded: next })
      // Stop audio when collapsing
      if (!next && this._audioCtx) {
        this._audioCtx.stop()
        this.setData({ isPlaying: false, playingType: '' })
      }
      this.triggerEvent('toggle', { expanded: next })
    },

    onPlayUS(e) {
      this._playAudio('us')
      if (e) e.stopPropagation && e.stopPropagation()
    },

    onPlayUK(e) {
      this._playAudio('uk')
      if (e) e.stopPropagation && e.stopPropagation()
    },

    _playAudio(type) {
      const word = (this.properties.word || '').trim()
      if (!word) return

      // If already playing same type, replay
      // If playing different type, switch
      const t = type === 'uk' ? 1 : 2
      const url = `https://dict.youdao.com/dictvoice?audio=${encodeURIComponent(word)}&type=${t}`

      if (this._audioCtx) {
        this._audioCtx.src = url
        this._audioCtx.play()
        this.setData({ isPlaying: true, playingType: type })
        // Haptic feedback
        wx.vibrateShort && wx.vibrateShort({ type: 'light' })
      }
    },

    normalizeContextMeanings(contextMeanings) {
      if (!Array.isArray(contextMeanings)) {
        return []
      }

      return contextMeanings
        .map((item) => {
          const context = String(item.context || '').trim()
          const meaning = String(item.meaning || '').trim()
          const example = String(item.example || '').trim()
          if (!meaning) {
            return null
          }
          return {
            context: this.localizeContext(context),
            meaning,
            example
          }
        })
        .filter(Boolean)
    },

    localizeContext(context) {
      const labels = {
        hotel: '酒店场景',
        phone: '电话沟通',
        email: '邮件表达',
        medical: '医疗预约',
        business: '商务场景',
        schedule: '日程安排',
        position: '职位任命',
        meeting: '会议安排',
        travel: '旅行场景',
        restaurant: '餐厅场景',
        daily: '日常表达',
        work: '职场表达',
        idea: '抽象表达',
        drink: '饮品场景'
      }
      const key = context.toLowerCase()
      return labels[key] || context || '常见语境'
    }
  }
})
