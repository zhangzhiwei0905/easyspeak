Component({
 properties: {
 phrase: {
 type: String,
 value: ''
 },
 meaning: {
 type: String,
 value: ''
 },
 explanation: {
 type: String,
 value: ''
 },
 examples: {
 type: Array,
 value: []
 },
 source: {
 type: String,
 value: ''
 },
 showDetail: {
 type: Boolean,
 value: false
 }
 },

  data: {
    expanded: false
  },

  observers: {
    'showDetail': function (val) {
      this.setData({ expanded: !!val })
    }
  },

  methods: {
    onTapCard() {
      const newExpanded = !this.data.expanded
      this.setData({ expanded: newExpanded })
      this.triggerEvent('toggle', { expanded: newExpanded })
    },

    onExampleTap(e) {
      const { index } = e.currentTarget.dataset
      this.triggerEvent('exampletap', { index })
    }
  }
})
