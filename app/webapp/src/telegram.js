/**
 * Telegram WebApp integration.
 * Safely wraps window.Telegram.WebApp.
 */

window.TG = (function () {
  const tg = window.Telegram && window.Telegram.WebApp;

  function init() {
    if (tg) {
      tg.ready();
      tg.expand();
    }
  }

  function getInitData() {
    return tg ? (tg.initData || "") : "";
  }

  function getUser() {
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
      return tg.initDataUnsafe.user;
    }
    return null;
  }

  function themeClass() {
    return tg && tg.colorScheme === "dark" ? "dark" : "light";
  }

  function showAlert(msg) {
    if (tg) tg.showAlert(msg);
    else alert(msg);
  }

  function haptic(type) {
    if (tg && tg.HapticFeedback) {
      if (type === "success") tg.HapticFeedback.notificationOccurred("success");
      else if (type === "error")  tg.HapticFeedback.notificationOccurred("error");
      else tg.HapticFeedback.impactOccurred("light");
    }
  }

  return { init, getInitData, getUser, themeClass, showAlert, haptic };
})();
