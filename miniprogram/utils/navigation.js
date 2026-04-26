function goToFallback(url, isTab) {
  if (!url) {
    return
  }

  if (isTab) {
    wx.switchTab({ url: url })
    return
  }

  wx.reLaunch({ url: url })
}

function safeNavigateBack(options) {
  var config = options || {}
  var delta = config.delta || 1
  var fallbackUrl = config.fallbackUrl || '/pages/index/index'
  var fallbackIsTab = config.fallbackIsTab !== false
  var pages = getCurrentPages()

  if (pages.length > delta) {
    wx.navigateBack({ delta: delta })
    return
  }

  goToFallback(fallbackUrl, fallbackIsTab)
}

module.exports = {
  safeNavigateBack: safeNavigateBack
}
