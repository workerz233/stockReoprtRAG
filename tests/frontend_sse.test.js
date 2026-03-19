const test = require("node:test");
const assert = require("node:assert/strict");

const { consumeSseStream } = require("../frontend/sse.js");

function createResponseWithReads(reads) {
  let index = 0;
  return {
    body: {
      getReader() {
        return {
          read() {
            const next = reads[index];
            index += 1;
            return next;
          },
          cancel() {
            return Promise.resolve();
          },
        };
      },
    },
  };
}

test("consumeSseStream resolves as soon as it receives a done event", async () => {
  const encoder = new TextEncoder();
  let sawDone = false;

  const response = createResponseWithReads([
    Promise.resolve({
      done: false,
      value: encoder.encode('event: done\ndata: {"answer":"ok"}\n\n'),
    }),
    new Promise(() => {}),
  ]);

  await Promise.race([
    consumeSseStream(response, {
      done(payload) {
        sawDone = payload.answer === "ok";
      },
    }),
    new Promise((_, reject) => {
      setTimeout(() => reject(new Error("consumeSseStream did not finish after done event")), 50);
    }),
  ]);

  assert.equal(sawDone, true);
});
