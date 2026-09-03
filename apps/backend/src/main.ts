import { Configuration } from './config.js';
import { Database } from './db/client.js';
import { NeonIdentityVerifier } from './identity/neon-identity-token.js';
import { HawkVanceServer } from './server.js';

const configuration = Configuration.fromProcessEnv();
const database = Database.connect(configuration.environment.DATABASE_URL);
const server = await HawkVanceServer.assemble(
  configuration,
  database,
  NeonIdentityVerifier.forJwksUrl(
    configuration.environment.NEON_JWKS_URL,
    configuration.identityIssuer,
  ),
);

const address = await server.listen(
  configuration.environment.HOST,
  configuration.environment.PORT,
);
server.fastify.log.info({ address }, 'HawkVance API listening');

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.once(signal, () => {
    server.fastify.log.info({ signal }, 'shutting down');
    void server.shutdown().then(() => process.exit(0));
  });
}
