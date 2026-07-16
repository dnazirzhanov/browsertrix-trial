(function(){
  const interval = setInterval(function() {
    /** @var {HTMLLinkElement} styleJs */
    const stylesJs = document.querySelector('link[href^="styles"][href$=".css"]');
    /** @var {HTMLScriptElement} styleJs */
    const mainJs = document.querySelector('script[src^="main"][src$=".js"]');
    if (stylesJs) {
      clearInterval(interval);
      removeInitLoader();
    } else if (mainJs) {
      clearInterval(interval);
      mainJs.onload = removeInitLoader;
    }
  }, 500);

  let safetyTimeout = setTimeout(function() {
    removeInitLoader();
  }, 3000);

  function removeInitLoader() {
    if (safetyTimeout) {
      clearTimeout(safetyTimeout);
    }

    const loader = document.getElementById('init-loader');
    if (loader) {
      loader.parentNode.removeChild(loader);
    }
  }
})()
