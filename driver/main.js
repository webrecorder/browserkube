const { Driver } = require("./driver");
const { EmbedDriver } = require("./embedsdriver");


// ================================================================================================
async function main() {
  let driver = null;

  let captureUrl;
  let storageUrl;
  captureUrl = process.env.CAPTURE_URL || (process.argv.length > 2 ? process.argv[2] : null);
  storageUrl = process.env.STORAGE_URL;

  if (process.env.EMBEDS) {
    driver = new EmbedDriver(captureUrl, storageUrl);
  } else {
    driver = new Driver(captureUrl, storageUrl);
  }

  driver.run();
}


main();

