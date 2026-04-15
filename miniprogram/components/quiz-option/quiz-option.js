Component({
  properties: {
    key: {
      type: String,
      value: 'A'
    },
    text: {
      type: String,
      value: ''
    },
    selected: {
      type: Boolean,
      value: false
    },
    correct: {
      type: Boolean,
      value: false
    },
    showResult: {
      type: Boolean,
      value: false
    },
    disabled: {
      type: Boolean,
      value: false
    }
  },

  methods: {
    onTapOption() {
      if (this.data.disabled) return
      this.triggerEvent('select', { key: this.data.key })
    }
  }
})
