using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Messages;
using Microsoft.Xrm.Sdk.Query;
using Moq;
using QueueFramework.Plugins;
using Xunit;

namespace QueueFramework.Tests;

public class BusinessEvidenceTests
{
    [Fact]
    public void GetBusinessUsesPrimaryIdAndReturnsPrimaryIdAsRowKey()
    {
        var id = Guid.NewGuid();
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(s => s.RetrieveMultiple(It.Is<QueryBase>(q => IsBusinessIdQuery(q, id))))
            .Returns(new EntityCollection(new List<Entity> { Business(id, "business-key", "1") }));

        var row = new DataverseStore(service.Object, new Mock<IPluginExecutionContext>().Object).Get("business", id.ToString());

        Assert.NotNull(row);
        Assert.Equal(id.ToString(), row!.Key);
        service.Verify(s => s.RetrieveMultiple(It.Is<QueryBase>(q => IsBusinessIdQuery(q, id))), Times.Once);
    }

    [Fact]
    public void DeleteBusinessUsesPrimaryIdAndPreservesRowVersionConcurrency()
    {
        var id = Guid.NewGuid();
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(s => s.RetrieveMultiple(It.Is<QueryBase>(q => IsBusinessIdQuery(q, id))))
            .Returns(new EntityCollection(new List<Entity> { Business(id, "different-business-key", "17") }));
        service.Setup(s => s.Execute(It.Is<DeleteRequest>(r =>
            r.ConcurrencyBehavior == ConcurrencyBehavior.IfRowVersionMatches &&
            r.Target.LogicalName == "qmcp_emailrequest" && r.Target.Id == id && r.Target.RowVersion == "17")))
            .Returns(new OrganizationResponse());

        new DataverseStore(service.Object, new Mock<IPluginExecutionContext>().Object).Delete("business", id.ToString(), 17);

        service.Verify(s => s.Execute(It.Is<DeleteRequest>(r =>
            r.ConcurrencyBehavior == ConcurrencyBehavior.IfRowVersionMatches &&
            r.Target.LogicalName == "qmcp_emailrequest" && r.Target.Id == id && r.Target.RowVersion == "17")), Times.Once);
    }

    [Fact]
    public void PageBusinessUsesPrimaryIdCursorAndOrdering()
    {
        var cursor = Guid.NewGuid();
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(s => s.RetrieveMultiple(It.Is<QueryBase>(q => IsBusinessPageQuery(q, cursor))))
            .Returns(new EntityCollection());

        var rows = new DataverseStore(service.Object, new Mock<IPluginExecutionContext>().Object)
            .Page("business", "mail", cursor.ToString(), 10);

        Assert.Empty(rows);
        service.Verify(s => s.RetrieveMultiple(It.Is<QueryBase>(q => IsBusinessPageQuery(q, cursor))), Times.Once);
    }

    [Fact]
    public void PageBusinessRejectsInvalidPrimaryIdCursor()
    {
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        var store = new DataverseStore(service.Object, new Mock<IPluginExecutionContext>().Object);

        Assert.Equal("INPUT_INVALID", Assert.Throws<Fault>(() => store.Page("business", "mail", "not-a-guid", 10)).Code);
        service.VerifyNoOtherCalls();
    }

    static bool IsBusinessIdQuery(QueryBase query, Guid id)
    {
        var q = Assert.IsType<QueryExpression>(query);
        return q.EntityName == "qmcp_emailrequest" && q.Criteria.Conditions.Count == 1 &&
            q.Criteria.Conditions[0].AttributeName == "qmcp_emailrequestid" &&
            q.Criteria.Conditions[0].Operator == ConditionOperator.Equal &&
            (Guid)q.Criteria.Conditions[0].Values[0] == id;
    }

    static bool IsBusinessPageQuery(QueryBase query, Guid cursor)
    {
        var q = Assert.IsType<QueryExpression>(query);
        return q.EntityName == "qmcp_emailrequest" && q.Criteria.Conditions.Count == 2 &&
            q.Criteria.Conditions.Any(c => c.AttributeName == "qmcp_queuekey" && (string)c.Values[0] == "mail") &&
            q.Criteria.Conditions.Any(c => c.AttributeName == "qmcp_emailrequestid" && c.Operator == ConditionOperator.GreaterThan && (Guid)c.Values[0] == cursor) &&
            q.Orders.Count == 1 && q.Orders[0].AttributeName == "qmcp_emailrequestid" && q.Orders[0].OrderType == OrderType.Ascending;
    }

    static Entity Business(Guid id, string key, string version)
    {
        var entity = new Entity("qmcp_emailrequest", id) { RowVersion = version };
        entity["qmcp_key"] = key;
        entity["qmcp_queuekey"] = "mail";
        entity["qmcp_document"] = "{}";
        return entity;
    }
}
