Component({
  properties: {
    word: {
      type: String,
      value: ''
    },
    phonetic: {
      type: String,
      value: ''
    },
    partOfSpeech: {
      type: String,
      value: ''
    },
    meaning: {
      type: String,
      value: ''
    },
    example: {
      type: String,
      value: ''
    }
  },

  data: {
    flipped: false,
    animating: false
  },

  methods: {
    onTapCard() {
      if (this.data.animating) return
      this.setData({ animating: true })
      const newFlipped = !this.data.flipped
      this.setData({ flipped: newFlipped })
      this.triggerEvent('flip', { flipped: newFlipped })

      setTimeout(() => {
        this.setData({ animating: false })
      }, 600)
    }
  }
})
