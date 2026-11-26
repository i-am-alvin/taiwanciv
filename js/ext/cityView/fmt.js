// Number formatting for the City View. format.js already rolls a value over to the next unit (9999.6萬 reads 1億,
// never 10000萬), so these are the shared helpers under the names the City View imports.
export { compact, money, yieldValue, popShort } from "../../format.js";
