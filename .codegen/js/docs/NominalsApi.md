# SnippetsApi.NominalsApi

All URIs are relative to *http://127.0.0.1:8000*

Method | HTTP request | Description
------------- | ------------- | -------------
[**nominalsCreate**](NominalsApi.md#nominalsCreate) | **POST** /nominals/nominal-list{format} | 
[**nominalsList**](NominalsApi.md#nominalsList) | **GET** /nominals/ | 
[**nominalsNominalListCreate**](NominalsApi.md#nominalsNominalListCreate) | **POST** /nominals/nominal-list | 
[**nominalsNominalListList**](NominalsApi.md#nominalsNominalListList) | **GET** /nominals/nominal-list | 
[**nominalsNominalsDelete**](NominalsApi.md#nominalsNominalsDelete) | **DELETE** /nominals/nominals/{id}/ | 
[**nominalsNominalsDelete_0**](NominalsApi.md#nominalsNominalsDelete_0) | **DELETE** /nominals/nominals/{id}{format} | 
[**nominalsNominalsPartialUpdate**](NominalsApi.md#nominalsNominalsPartialUpdate) | **PATCH** /nominals/nominals/{id}/ | 
[**nominalsNominalsPartialUpdate_0**](NominalsApi.md#nominalsNominalsPartialUpdate_0) | **PATCH** /nominals/nominals/{id}{format} | 
[**nominalsNominalsRead**](NominalsApi.md#nominalsNominalsRead) | **GET** /nominals/nominals/{id}/ | 
[**nominalsNominalsRead_0**](NominalsApi.md#nominalsNominalsRead_0) | **GET** /nominals/nominals/{id}{format} | 
[**nominalsNominalsUpdate**](NominalsApi.md#nominalsNominalsUpdate) | **PUT** /nominals/nominals/{id}/ | 
[**nominalsNominalsUpdate_0**](NominalsApi.md#nominalsNominalsUpdate_0) | **PUT** /nominals/nominals/{id}{format} | 
[**nominalsRead**](NominalsApi.md#nominalsRead) | **GET** /nominals/nominal-list{format} | 
[**nominalsRead_0**](NominalsApi.md#nominalsRead_0) | **GET** /nominals/{format} | 


<a name="nominalsCreate"></a>
# **nominalsCreate**
> Nominal nominalsCreate(format, data)





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var format = "format_example"; // String | 

var data = new SnippetsApi.Nominal(); // Nominal | 


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsCreate(format, data, callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **format** | **String**|  | 
 **data** | [**Nominal**](Nominal.md)|  | 

### Return type

[**Nominal**](Nominal.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsList"></a>
# **nominalsList**
> nominalsList()





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully.');
  }
};
apiInstance.nominalsList(callback);
```

### Parameters
This endpoint does not need any parameter.

### Return type

null (empty response body)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalListCreate"></a>
# **nominalsNominalListCreate**
> Nominal nominalsNominalListCreate(data)





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var data = new SnippetsApi.Nominal(); // Nominal | 


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsNominalListCreate(data, callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **data** | [**Nominal**](Nominal.md)|  | 

### Return type

[**Nominal**](Nominal.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalListList"></a>
# **nominalsNominalListList**
> InlineResponse200 nominalsNominalListList(opts)





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var opts = { 
  'page': 56 // Number | A page number within the paginated result set.
};

var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsNominalListList(opts, callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **page** | **Number**| A page number within the paginated result set. | [optional] 

### Return type

[**InlineResponse200**](InlineResponse200.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalsDelete"></a>
# **nominalsNominalsDelete**
> nominalsNominalsDelete(id, )





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var id = 56; // Number | A unique integer value identifying this nominal.


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully.');
  }
};
apiInstance.nominalsNominalsDelete(id, , callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **Number**| A unique integer value identifying this nominal. | 

### Return type

null (empty response body)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalsDelete_0"></a>
# **nominalsNominalsDelete_0**
> nominalsNominalsDelete_0(format, id, )





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var format = "format_example"; // String | 

var id = 56; // Number | A unique integer value identifying this nominal.


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully.');
  }
};
apiInstance.nominalsNominalsDelete_0(format, id, , callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **format** | **String**|  | 
 **id** | **Number**| A unique integer value identifying this nominal. | 

### Return type

null (empty response body)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalsPartialUpdate"></a>
# **nominalsNominalsPartialUpdate**
> Nominal nominalsNominalsPartialUpdate(id, data)





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var id = 56; // Number | A unique integer value identifying this nominal.

var data = new SnippetsApi.Nominal(); // Nominal | 


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsNominalsPartialUpdate(id, data, callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **Number**| A unique integer value identifying this nominal. | 
 **data** | [**Nominal**](Nominal.md)|  | 

### Return type

[**Nominal**](Nominal.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalsPartialUpdate_0"></a>
# **nominalsNominalsPartialUpdate_0**
> Nominal nominalsNominalsPartialUpdate_0(format, id, data)





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var format = "format_example"; // String | 

var id = 56; // Number | A unique integer value identifying this nominal.

var data = new SnippetsApi.Nominal(); // Nominal | 


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsNominalsPartialUpdate_0(format, id, data, callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **format** | **String**|  | 
 **id** | **Number**| A unique integer value identifying this nominal. | 
 **data** | [**Nominal**](Nominal.md)|  | 

### Return type

[**Nominal**](Nominal.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalsRead"></a>
# **nominalsNominalsRead**
> Nominal nominalsNominalsRead(id, )





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var id = 56; // Number | A unique integer value identifying this nominal.


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsNominalsRead(id, , callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **Number**| A unique integer value identifying this nominal. | 

### Return type

[**Nominal**](Nominal.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalsRead_0"></a>
# **nominalsNominalsRead_0**
> Nominal nominalsNominalsRead_0(format, id, )





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var format = "format_example"; // String | 

var id = 56; // Number | A unique integer value identifying this nominal.


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsNominalsRead_0(format, id, , callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **format** | **String**|  | 
 **id** | **Number**| A unique integer value identifying this nominal. | 

### Return type

[**Nominal**](Nominal.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalsUpdate"></a>
# **nominalsNominalsUpdate**
> Nominal nominalsNominalsUpdate(id, data)





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var id = 56; // Number | A unique integer value identifying this nominal.

var data = new SnippetsApi.Nominal(); // Nominal | 


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsNominalsUpdate(id, data, callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **Number**| A unique integer value identifying this nominal. | 
 **data** | [**Nominal**](Nominal.md)|  | 

### Return type

[**Nominal**](Nominal.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsNominalsUpdate_0"></a>
# **nominalsNominalsUpdate_0**
> Nominal nominalsNominalsUpdate_0(format, id, data)





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var format = "format_example"; // String | 

var id = 56; // Number | A unique integer value identifying this nominal.

var data = new SnippetsApi.Nominal(); // Nominal | 


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsNominalsUpdate_0(format, id, data, callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **format** | **String**|  | 
 **id** | **Number**| A unique integer value identifying this nominal. | 
 **data** | [**Nominal**](Nominal.md)|  | 

### Return type

[**Nominal**](Nominal.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsRead"></a>
# **nominalsRead**
> InlineResponse200 nominalsRead(format, , opts)





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var format = "format_example"; // String | 

var opts = { 
  'page': 56 // Number | A page number within the paginated result set.
};

var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully. Returned data: ' + data);
  }
};
apiInstance.nominalsRead(format, , opts, callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **format** | **String**|  | 
 **page** | **Number**| A page number within the paginated result set. | [optional] 

### Return type

[**InlineResponse200**](InlineResponse200.md)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a name="nominalsRead_0"></a>
# **nominalsRead_0**
> nominalsRead_0(format)





### Example
```javascript
var SnippetsApi = require('snippets_api');
var defaultClient = SnippetsApi.ApiClient.instance;

// Configure HTTP basic authorization: Basic
var Basic = defaultClient.authentications['Basic'];
Basic.username = 'YOUR USERNAME';
Basic.password = 'YOUR PASSWORD';

var apiInstance = new SnippetsApi.NominalsApi();

var format = "format_example"; // String | 


var callback = function(error, data, response) {
  if (error) {
    console.error(error);
  } else {
    console.log('API called successfully.');
  }
};
apiInstance.nominalsRead_0(format, callback);
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **format** | **String**|  | 

### Return type

null (empty response body)

### Authorization

[Basic](../README.md#Basic)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

