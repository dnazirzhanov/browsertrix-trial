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
    clearInterval(interval);
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

  /**
   * Due to some caching issues the old index.html could be cached for 1 year.
   * This is a big problem for as it would not update to the latest version of the site.
   * As the cache for the init loader is only 300 sec, we can make a redirect to the root / page to circumvent this issue.
   */
  function checkIndexHtmlCacheRedirect() {
    const url = window.location.href;
    if(url.endsWith('/index.html')) {
      window.location.href = url.replace('/index.html', '');
    }
  }
  checkIndexHtmlCacheRedirect();
})()
