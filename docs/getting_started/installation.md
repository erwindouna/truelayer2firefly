You can install the application via Docker Compose or via the Docker command:

### Docker compose
```dockerfile
services:
  truelayer2firefly:
    iimage: erwind/truelayer2firefly:latest
    container_name: truelayer2firefly
    ports:
      - "3000:3000" # Update this to your desired port
    volumes:
      - /YOUR_MOUNT:/app/data # Update this to your mount point
```

### Docker command
```dockerfile
docker run -d \
  --name truelayer2firefly \
  -p 3000:3000 \
  -v /YOUR_MOUNT:/app/data \
  erwind/truelayer2firefly:latest
```

## Configuration
The application will create a basic configuration file to store your settings.

### Firefly III
Follow these steps to set up your Firefly III instance:

1. Create an OAuth Client in your Firefly III instance. You can do this by going to
`Profile > OAuth > OAuth Clients` and clicking on `Create OAuth Client`. Make sure to **uncheck** the `Confidential` option.
2. Fill in the `Name` and `Redirect URI` fields. The `Redirect URL` should be set to `http://{YOUR_HOST}:{YOUR_PORT}/auth/firefly/callback`. For example, if you are running the application on `localhost` and port `3000`, the redirect URL would be `http://localhost:3000/auth/firefly/callback`. This needs to **100%** match the URL you are using to access the application.
3. In TrueLayer2Firefly, fill in the `API URL` with the URL of your Firefly III instance. For example, if you are running Firefly III on `localhost` and port `8080`, the API URL would be `http://localhost:8080`. Also fill in the `Client ID`. You will now be guided through the OAuth flow to authorize the application to access your Firefly III instance.
4. On completion, you will be redirected to the application and your Firefly III instance will be connected.

### TrueLayer
Follow these steps to set up your TrueLayer instance. This is a bit more complicated, so follow these steps carefully. You can find more information on the [TrueLayer documentation](https://docs.truelayer.com/).

1. Create an application in the [TrueLayer dashboard](https://console.truelayer.com/) (sign up if you don't have an account yet).
2. Switch your application to `Live` mode. This is done by clicking on the `Switch to Live` button in the top right corner of the dashboard. You can confirm if you're in `Live` mode by checking the the `Client ID`. This should **not** start with `sandbox-`.
2. Find your `Client ID` and `Client Secret` in the application settings. These can be found in the `Settings` tab of your application. If you forgot somehow your `Client Secret`, you can regenerate it in the `Settings` tab.
3. In the `Redirect URI` field, fill in the URL of your TrueLayer2Firefly instance. For example, if you are running the application on `localhost` and port `3000`, the redirect URL would be `http://localhost:3000/auth/truelayer/callback`. This needs to **100%** match the URL you are using to access the application.
4. In TrueLayer2Firefly, fill in the `Client ID`,`Client Secret`, `Redirect URI` with the values from the TrueLayer dashboard. Again, this needs to **100%** match the URL you are using to access the application. You will now be guided through the OAuth flow to authorize the application to access your TrueLayer instance. You can filter per country and then find the banking institutions you want to connect to.
5. From here, follow the instructions in the application to connect your bank accounts.
6. On completion, you will be redirected to the application and your bank accounts will be connected. You can now start synchronizing your transactions!

## Troubleshooting
If you run into issues, you can reset your configuration by deleting the `config.json` file in the `data` folder. This will reset all your settings and you will have to reconfigure the application. Or, the more userfriendly way, goto `Configuration` and click on `Reset Configuration`. This will reset all your settings and you will have to reconfigure the application.