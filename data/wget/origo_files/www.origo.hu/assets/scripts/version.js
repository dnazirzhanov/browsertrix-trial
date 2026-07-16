fetch('/assets/scripts/version.txt')
  .then(response => response.text())
  .then(version =>
    console.log(`%c VERZIÓ: ${version}`, 'color: white; background: darkgreen; display: block; padding: 2px')
  );
