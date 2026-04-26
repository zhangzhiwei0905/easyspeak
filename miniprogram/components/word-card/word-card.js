Component({
  properties: {
    word: { type: String, value: '' },
    phonetic: { type: String, value: '' },
    partOfSpeech: { type: String, value: '' },
    meaning: { type: String, value: '' },
    example: { type: String, value: '' }
  },

  data: {
    expanded: false
  },

  methods: {
    onTapCard() {
      this.setData({ expanded: !this.data.expanded })
      this.triggerEvent('toggle', { expanded: !this.data.expanded })
    }
  }
})
